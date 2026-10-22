import json
from pathlib import Path

from aneel_rag.chunking.fixed import chunk_fixed
from aneel_rag.chunking.models import Chunk
from aneel_rag.chunking.structural import chunk_structural
from aneel_rag.config.settings import ChunkingConfig
from aneel_rag.ingest.models import Unit


def build_chunks(units: list[Unit], cfg: ChunkingConfig) -> list[Chunk]:
    if cfg.strategy == "fixed":
        return chunk_fixed(units, cfg.fixed_size, cfg.fixed_overlap)
    return chunk_structural(units, cfg.max_chars)


def load_units(path: Path) -> list[Unit]:
    with open(path, encoding="utf-8") as fh:
        return [Unit.model_validate(json.loads(line)) for line in fh if line.strip()]


__all__ = ["Chunk", "build_chunks", "load_units"]
