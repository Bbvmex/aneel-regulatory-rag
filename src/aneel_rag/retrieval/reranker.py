"""Cross-encoder reranking of the fused candidates."""

import re
from typing import Protocol


class Reranker(Protocol):
    def score(self, query: str, texts: list[str]) -> list[float]: ...


class BGEReranker:
    def __init__(self, model_id: str, revision: str, max_length: int, batch_size: int):
        from FlagEmbedding import FlagReranker  # heavy, local-only dependency (ml group)

        from aneel_rag.retrieval.hub import local_model_path

        self._model = FlagReranker(
            local_model_path(model_id, revision),
            use_fp16=False,
            devices="cpu",
            max_length=max_length,
            batch_size=batch_size,
        )

    def score(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        scores = self._model.compute_score([(query, t) for t in texts], normalize=True)
        return [float(s) for s in scores]


class OverlapReranker:
    """Word-overlap scorer for tests; deterministic and model-free."""

    def score(self, query: str, texts: list[str]) -> list[float]:
        words = set(re.findall(r"\w+", query.casefold()))
        return [
            len(words & set(re.findall(r"\w+", t.casefold()))) / (len(words) or 1) for t in texts
        ]
