import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "default.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CorpusConfig(_Strict):
    path: Path


class ModelsConfig(_Strict):
    generator: str
    judge: str
    embedding: str
    reranker: str

    @field_validator("generator", "judge")
    @classmethod
    def _pinned_id(cls, value: str) -> str:
        # Floating aliases would silently change results between runs.
        if value.endswith("-latest"):
            raise ValueError(f"model alias '{value}' is not allowed; pin an exact model ID")
        return value


class QdrantConfig(_Strict):
    collection: str


class RetrievalConfig(_Strict):
    mode: Literal["dense", "sparse", "hybrid", "hybrid+rerank"]
    k_dense: int
    k_sparse: int
    k_rerank: int
    include_revoked: bool = False
    include_annexes: bool = False


class ChunkingConfig(_Strict):
    strategy: Literal["structural", "fixed"]


class GenerationConfig(_Strict):
    temperature: float
    max_citation_retries: int


class CitationsConfig(_Strict):
    min_quote_chars: int
    max_quote_chars: int


class AppConfig(_Strict):
    corpus: CorpusConfig
    models: ModelsConfig
    qdrant: QdrantConfig
    retrieval: RetrievalConfig
    chunking: ChunkingConfig
    generation: GenerationConfig
    citations: CitationsConfig


class Secrets(BaseSettings):
    """Secrets and endpoints from the environment / .env; never part of the config hash."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    llm_base_url: str = ""
    llm_api_key: str = ""
    judge_base_url: str = ""
    judge_api_key: str = ""
    local_llm_base_url: str = ""
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = ""
    log_level: str = "INFO"


def load_config(path: Path | str = DEFAULT_CONFIG) -> AppConfig:
    with open(path, encoding="utf-8") as fh:
        return AppConfig.model_validate(yaml.safe_load(fh))


@lru_cache
def get_secrets() -> Secrets:
    return Secrets()


def config_hash(cfg: AppConfig, length: int = 12) -> str:
    canonical = json.dumps(cfg.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:length]


def file_sha256(path: Path | str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def corpus_sha256(cfg: AppConfig) -> str:
    path = cfg.corpus.path
    return file_sha256(path if path.is_absolute() else PROJECT_ROOT / path)
