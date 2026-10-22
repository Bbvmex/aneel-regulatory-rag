"""python -m aneel_rag.retrieval.index: chunk the parsed units, embed them and load Qdrant."""

import json
import sys
import uuid
from pathlib import Path

from qdrant_client import QdrantClient, models

from aneel_rag.chunking import Chunk, build_chunks, load_units
from aneel_rag.config.settings import PROJECT_ROOT, AppConfig, get_secrets, load_config
from aneel_rag.retrieval.embedder import BGEM3Embedder, CachedEmbedder, Embedder

PROCESSED = PROJECT_ROOT / "data" / "processed"
CACHE = PROJECT_ROOT / "data" / "cache" / "embeddings.sqlite"


def collection_name(cfg: AppConfig) -> str:
    # One collection per chunking strategy, so the ablation does not overwrite the default.
    return f"{cfg.qdrant.collection}_{cfg.chunking.strategy}"


def point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def make_client() -> QdrantClient:
    secrets = get_secrets()
    return QdrantClient(url=secrets.qdrant_url, api_key=secrets.qdrant_api_key or None)


def make_embedder(cfg: AppConfig) -> CachedEmbedder:
    inner = BGEM3Embedder(cfg.models.embedding, cfg.embedding.batch_size, cfg.embedding.max_length)
    return CachedEmbedder(inner, CACHE, salt=f"max_length={cfg.embedding.max_length}")


def create_collection(client: QdrantClient, name: str, dim: int) -> None:
    if client.collection_exists(name):
        client.delete_collection(name)
    client.create_collection(
        name,
        vectors_config={"dense": models.VectorParams(size=dim, distance=models.Distance.COSINE)},
        sparse_vectors_config={"sparse": models.SparseVectorParams()},
    )
    for field in ("status", "doc_type"):
        client.create_payload_index(name, field, models.PayloadSchemaType.KEYWORD)


def index_chunks(
    client: QdrantClient, name: str, chunks: list[Chunk], embedder: Embedder, batch: int = 64
) -> None:
    create_collection(client, name, embedder.dim)
    for start in range(0, len(chunks), batch):
        part = chunks[start : start + batch]
        embs = embedder.embed_documents([c.text for c in part])
        points = [
            models.PointStruct(
                id=point_id(c.chunk_id),
                vector={
                    "dense": e.dense,
                    "sparse": models.SparseVector(
                        indices=list(e.sparse), values=list(e.sparse.values())
                    ),
                },
                payload=c.model_dump(mode="json"),
            )
            for c, e in zip(part, embs, strict=True)
        ]
        client.upsert(name, points=points)
        print(f"  {min(start + batch, len(chunks))}/{len(chunks)} chunks", flush=True)


def write_chunks(chunks: list[Chunk], path: Path) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False) + "\n")


def main() -> int:
    cfg = load_config()
    units_path = PROCESSED / "units.jsonl"
    if not units_path.exists():
        print(f"ERROR: {units_path} not found; run `make ingest` first", file=sys.stderr)
        return 1
    chunks = build_chunks(load_units(units_path), cfg.chunking)
    write_chunks(chunks, PROCESSED / f"chunks_{cfg.chunking.strategy}.jsonl")
    name = collection_name(cfg)
    print(f"{len(chunks)} {cfg.chunking.strategy} chunks -> Qdrant collection '{name}'")
    index_chunks(make_client(), name, chunks, make_embedder(cfg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
