"""What an index was built from, stored in the Qdrant collection metadata (ADR-003)."""

import hashlib
import json

from pydantic import BaseModel, ConfigDict, ValidationError
from qdrant_client import QdrantClient

from aneel_rag.config.settings import AppConfig, corpus_sha256
from aneel_rag.ingest.models import PARSER_VERSION


class IndexMismatchError(RuntimeError):
    pass


class IndexProvenance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    corpus_sha256: str
    parser_version: str
    index_config_hash: str


def index_config_hash(cfg: AppConfig, length: int = 12) -> str:
    # Only what changes the stored vectors and payloads; retrieval mode, k values and the
    # reranker are query-time choices, so the phase 5 ablations can reuse one index.
    scope = {
        "collection": cfg.qdrant.collection,
        "chunking": cfg.chunking.model_dump(mode="json"),
        "embedding_model": cfg.models.embedding,
        "embedding_revision": cfg.models.embedding_revision,
        "embedding_max_length": cfg.embedding.max_length,
    }
    canonical = json.dumps(scope, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:length]


def expected_provenance(cfg: AppConfig) -> IndexProvenance:
    return IndexProvenance(
        corpus_sha256=corpus_sha256(cfg),
        parser_version=PARSER_VERSION,
        index_config_hash=index_config_hash(cfg),
    )


def check_index(client: QdrantClient, collection: str, expected: IndexProvenance) -> None:
    if not client.collection_exists(collection):
        raise IndexMismatchError(f"collection '{collection}' not found; run `make index`")
    metadata = client.get_collection(collection).config.metadata or {}
    try:
        actual = IndexProvenance.model_validate(metadata)
    except ValidationError as exc:
        raise IndexMismatchError(
            f"collection '{collection}' has no provenance metadata; run `make index`"
        ) from exc
    diff = {
        field: (getattr(actual, field), value)
        for field, value in expected.model_dump().items()
        if getattr(actual, field) != value
    }
    if diff:
        detail = ", ".join(f"{k}: index={a} current={e}" for k, (a, e) in diff.items())
        raise IndexMismatchError(f"collection '{collection}' is stale ({detail}); run `make index`")
