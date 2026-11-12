"""Cross-encoder reranking of the fused candidates."""

import hashlib
import re
import sqlite3
from pathlib import Path
from typing import Protocol

from aneel_rag.config.settings import PROJECT_ROOT, AppConfig

CACHE = PROJECT_ROOT / "data" / "cache" / "rerank.sqlite"


class Reranker(Protocol):
    def score(self, query: str, texts: list[str]) -> list[float]: ...


class BGEReranker:
    def __init__(self, model_id: str, revision: str, max_length: int, batch_size: int):
        from FlagEmbedding import FlagReranker  # heavy, local-only dependency (ml group)

        from aneel_rag.retrieval.hub import local_model_path

        flag = FlagReranker(local_model_path(model_id, revision), use_fp16=False, devices="cpu")
        self._tokenizer, self._model = flag.tokenizer, flag.model.eval()
        self.max_length = max_length
        self.batch_size = batch_size

    def score(self, query: str, texts: list[str]) -> list[float]:
        """Own loop instead of FlagReranker.compute_score, which scores its first batch twice
        to probe the batch size; same scores (decision 49)."""
        import torch

        if not texts:
            return []
        ids = [
            self._tokenizer(query, t, truncation="only_second", max_length=self.max_length)[
                "input_ids"
            ]
            for t in texts
        ]
        # Longest first, so each batch pads to similar lengths.
        order = sorted(range(len(ids)), key=lambda i: -len(ids[i]))
        scores = [0.0] * len(ids)
        with torch.inference_mode():
            for start in range(0, len(order), self.batch_size):
                idx = order[start : start + self.batch_size]
                batch = self._tokenizer.pad(
                    {"input_ids": [ids[i] for i in idx]}, return_tensors="pt"
                )
                logits = self._model(**batch, return_dict=True).logits.view(-1).float()
                for i, s in zip(idx, torch.sigmoid(logits).tolist(), strict=True):
                    scores[i] = s
        return scores


class CachedReranker:
    """Scores cached in SQLite by (model, settings, query, chunk text): reruns are free."""

    def __init__(self, inner: Reranker, path: Path, salt: str):
        self.inner = inner
        self._salt = salt  # model ID, revision and max_length: anything that changes a score
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.execute("CREATE TABLE IF NOT EXISTS score (key TEXT PRIMARY KEY, value REAL)")
        self.hits = self.misses = 0

    def _key(self, query: str, text: str) -> str:
        raw = f"{self._salt}\x00{query}\x00{text}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def score(self, query: str, texts: list[str]) -> list[float]:
        keys = [self._key(query, t) for t in texts]
        marks = ",".join("?" * len(keys))
        found = dict(self._db.execute(f"SELECT key, value FROM score WHERE key IN ({marks})", keys))
        missing = list(dict.fromkeys(k for k in keys if k not in found))
        self.hits += len(keys) - len(missing)
        self.misses += len(missing)
        if missing:
            text_of = dict(zip(keys, texts, strict=True))
            fresh = self.inner.score(query, [text_of[k] for k in missing])
            rows = list(zip(missing, fresh, strict=True))
            self._db.executemany("INSERT OR REPLACE INTO score VALUES (?, ?)", rows)
            self._db.commit()
            found.update(rows)
        return [found[k] for k in keys]


def make_reranker(cfg: AppConfig, cache: Path = CACHE) -> CachedReranker:
    models, max_length = cfg.models, cfg.embedding.rerank_max_length
    inner = BGEReranker(
        models.reranker, models.reranker_revision, max_length, cfg.embedding.rerank_batch_size
    )
    salt = f"{models.reranker}@{models.reranker_revision}|max_length={max_length}"
    return CachedReranker(inner, cache, salt)


class OverlapReranker:
    """Word-overlap scorer for tests; deterministic and model-free."""

    def score(self, query: str, texts: list[str]) -> list[float]:
        words = set(re.findall(r"\w+", query.casefold()))
        return [
            len(words & set(re.findall(r"\w+", t.casefold()))) / (len(words) or 1) for t in texts
        ]
