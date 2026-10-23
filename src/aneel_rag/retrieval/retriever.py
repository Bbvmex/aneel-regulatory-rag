from pydantic import BaseModel
from qdrant_client import QdrantClient

from aneel_rag.chunking import Chunk
from aneel_rag.config.settings import RetrievalConfig
from aneel_rag.retrieval.embedder import Embedder
from aneel_rag.retrieval.modes import Mode, default_filter, search
from aneel_rag.retrieval.provenance import IndexProvenance, check_index
from aneel_rag.retrieval.reranker import Reranker


class Hit(BaseModel):
    rank: int
    score: float  # cosine, sparse dot product, RRF or reranker score, depending on the mode
    chunk: Chunk


class Retriever:
    def __init__(
        self,
        client: QdrantClient,
        collection: str,
        embedder: Embedder,
        cfg: RetrievalConfig,
        reranker: Reranker | None = None,
        expected: IndexProvenance | None = None,
    ):
        """With `expected`, refuse an index built from another corpus, parser or index config."""
        if expected is not None:
            check_index(client, collection, expected)
        self.client = client
        self.collection = collection
        self.embedder = embedder
        self.cfg = cfg
        self.reranker = reranker

    def search(
        self,
        query: str,
        mode: Mode | None = None,
        k: int | None = None,
        include_revoked: bool | None = None,
        include_annexes: bool | None = None,
    ) -> list[Hit]:
        """Arguments left as None fall back to the retrieval config."""
        cfg = self.cfg
        mode = mode or cfg.mode
        k = k or cfg.k_final
        flt = default_filter(
            cfg.include_revoked if include_revoked is None else include_revoked,
            cfg.include_annexes if include_annexes is None else include_annexes,
        )
        rerank = mode == "hybrid+rerank"
        if rerank and self.reranker is None:
            raise ValueError("mode 'hybrid+rerank' needs a reranker")
        points = search(
            self.client,
            self.collection,
            "hybrid" if rerank else mode,
            self.embedder.embed_query(query),
            max(k, cfg.k_candidates) if rerank else k,
            cfg.k_dense,
            cfg.k_sparse,
            flt,
        )
        scored = [(p.score, Chunk.model_validate(p.payload)) for p in points]
        if rerank:
            scores = self.reranker.score(query, [c.text for _, c in scored])
            # Stable sort: ties keep the fused order.
            order = sorted(range(len(scored)), key=lambda i: -scores[i])
            scored = [(scores[i], scored[i][1]) for i in order]
        return [Hit(rank=i + 1, score=s, chunk=c) for i, (s, c) in enumerate(scored[:k])]
