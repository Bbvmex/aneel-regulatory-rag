"""Dense + sparse (lexical) embeddings from bge-m3, with a disk cache keyed by text hash."""

import hashlib
import json
import math
import re
import sqlite3
from pathlib import Path
from typing import NamedTuple, Protocol


class Embedding(NamedTuple):
    dense: list[float]
    sparse: dict[int, float]  # token id -> lexical weight


class Embedder(Protocol):
    model_id: str
    dim: int

    def embed_documents(self, texts: list[str]) -> list[Embedding]: ...

    def embed_query(self, text: str) -> Embedding: ...


class BGEM3Embedder:
    dim = 1024

    def __init__(self, model_id: str, revision: str, batch_size: int, max_length: int):
        from FlagEmbedding import BGEM3FlagModel  # heavy, local-only dependency (ml group)

        from aneel_rag.retrieval.hub import local_model_path

        # The revision is part of the id, so the embedding cache never mixes model versions.
        self.model_id = f"{model_id}@{revision}"
        self.batch_size = batch_size
        self.max_length = max_length
        path = local_model_path(model_id, revision)
        self._model = BGEM3FlagModel(path, use_fp16=False, devices="cpu")

    def _encode(self, texts: list[str]) -> list[Embedding]:
        out = self._model.encode(
            texts,
            batch_size=self.batch_size,
            max_length=self.max_length,
            return_dense=True,
            return_sparse=True,
        )
        return [
            Embedding(dense.tolist(), {int(k): float(v) for k, v in weights.items()})
            for dense, weights in zip(out["dense_vecs"], out["lexical_weights"], strict=True)
        ]

    def embed_documents(self, texts: list[str]) -> list[Embedding]:
        return self._encode(texts)

    def embed_query(self, text: str) -> Embedding:
        return self._encode([text])[0]


class HashEmbedder:
    """Deterministic bag-of-words embedder for tests and CI; no model download."""

    model_id = "hash-bow"

    def __init__(self, dim: int = 64):
        self.dim = dim

    @staticmethod
    def _tokens(text: str) -> list[int]:
        words = re.findall(r"\w+", text.casefold())
        return [int(hashlib.md5(w.encode()).hexdigest()[:8], 16) for w in words]

    def _embed(self, text: str) -> Embedding:
        sparse: dict[int, float] = {}
        dense = [0.0] * self.dim
        for token in self._tokens(text):
            sparse[token] = sparse.get(token, 0.0) + 1.0
            dense[token % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in dense)) or 1.0
        return Embedding([x / norm for x in dense], sparse)

    def embed_documents(self, texts: list[str]) -> list[Embedding]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> Embedding:
        return self._embed(text)


class CachedEmbedder:
    """Wraps an embedder; document embeddings are cached in SQLite by (model, text) hash."""

    def __init__(self, inner: Embedder, path: Path, salt: str = ""):
        self.inner = inner
        self.model_id = inner.model_id
        self.dim = inner.dim
        self._salt = salt  # anything else that changes the vectors, e.g. max_length
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.execute("CREATE TABLE IF NOT EXISTS emb (key TEXT PRIMARY KEY, value TEXT)")

    def _key(self, text: str) -> str:
        raw = f"{self.model_id}\x00{self._salt}\x00{text}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def embed_documents(self, texts: list[str]) -> list[Embedding]:
        keys = [self._key(t) for t in texts]
        found = {}
        for i in range(0, len(keys), 500):
            batch = keys[i : i + 500]
            marks = ",".join("?" * len(batch))
            rows = self._db.execute(f"SELECT key, value FROM emb WHERE key IN ({marks})", batch)
            found.update(rows)
        missing = list(dict.fromkeys(k for k in keys if k not in found))
        if missing:
            text_of = dict(zip(keys, texts, strict=True))
            fresh = self.inner.embed_documents([text_of[k] for k in missing])
            rows = [
                (k, json.dumps([e.dense, list(e.sparse.items())]))
                for k, e in zip(missing, fresh, strict=True)
            ]
            self._db.executemany("INSERT OR REPLACE INTO emb VALUES (?, ?)", rows)
            self._db.commit()
            found.update(rows)
        result = []
        for key in keys:
            dense, sparse = json.loads(found[key])
            result.append(Embedding(dense, {int(k): v for k, v in sparse}))
        return result

    def embed_query(self, text: str) -> Embedding:
        return self.inner.embed_query(text)
