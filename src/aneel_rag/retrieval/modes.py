"""Qdrant queries for each retrieval mode (ADR-003)."""

from typing import Literal

from qdrant_client import QdrantClient, models

from aneel_rag.retrieval.embedder import Embedding

Mode = Literal["dense", "sparse", "hybrid", "hybrid+rerank"]
MODES: tuple[Mode, ...] = ("dense", "sparse", "hybrid", "hybrid+rerank")


def default_filter(include_revoked: bool, include_annexes: bool) -> models.Filter | None:
    must = [] if include_annexes else [_match("doc_type", "norm")]
    must_not = [] if include_revoked else [_match("status", "revoked")]
    if not must and not must_not:
        return None
    return models.Filter(must=must or None, must_not=must_not or None)


def _match(key: str, value: str) -> models.FieldCondition:
    return models.FieldCondition(key=key, match=models.MatchValue(value=value))


def _sparse(emb: Embedding) -> models.SparseVector:
    keys = sorted(emb.sparse)
    return models.SparseVector(indices=keys, values=[emb.sparse[k] for k in keys])


def search(
    client: QdrantClient,
    collection: str,
    mode: Mode,
    emb: Embedding,
    limit: int,
    k_dense: int,
    k_sparse: int,
    flt: models.Filter | None,
) -> list[models.ScoredPoint]:
    """Candidates for one mode; hybrid+rerank uses the hybrid pool and reranks it elsewhere."""
    common = {"collection_name": collection, "query_filter": flt, "with_payload": True}
    if mode == "dense":
        return client.query_points(query=emb.dense, using="dense", limit=limit, **common).points
    if mode == "sparse":
        if not emb.sparse:  # e.g. a query of stopwords only
            return []
        return client.query_points(query=_sparse(emb), using="sparse", limit=limit, **common).points
    # Fusion is done server side with Reciprocal Rank Fusion over both prefetches.
    prefetch = [models.Prefetch(query=emb.dense, using="dense", limit=k_dense, filter=flt)]
    if emb.sparse:
        prefetch.append(
            models.Prefetch(query=_sparse(emb), using="sparse", limit=k_sparse, filter=flt)
        )
    fusion = models.FusionQuery(fusion=models.Fusion.RRF)
    return client.query_points(prefetch=prefetch, query=fusion, limit=limit, **common).points
