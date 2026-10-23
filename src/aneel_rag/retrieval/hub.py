"""python -m aneel_rag.retrieval.hub: download the pinned models once; later loads stay offline."""

import sys
from pathlib import Path

from aneel_rag.config.settings import load_config

# Weights, tokenizer and the bge-m3 sparse/colbert heads; skips ONNX exports and README images.
ALLOW_PATTERNS = ["*.json", "*.bin", "*.safetensors", "*.pt", "*.model"]


class ModelNotCachedError(RuntimeError):
    pass


def local_model_path(repo_id: str, revision: str, cache_dir: Path | None = None) -> str:
    """Snapshot directory of a pinned revision, from the local cache only (never the Hub)."""
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import LocalEntryNotFoundError

    try:
        return snapshot_download(
            repo_id,
            revision=revision,
            cache_dir=cache_dir,
            allow_patterns=ALLOW_PATTERNS,
            local_files_only=True,
        )
    except LocalEntryNotFoundError as exc:
        raise ModelNotCachedError(
            f"{repo_id}@{revision[:8]} is not in the local Hugging Face cache; "
            "run `make models` once (needs network)"
        ) from exc


def main() -> int:
    from huggingface_hub import snapshot_download

    models = load_config().models
    for repo_id, revision in (
        (models.embedding, models.embedding_revision),
        (models.reranker, models.reranker_revision),
    ):
        path = snapshot_download(repo_id, revision=revision, allow_patterns=ALLOW_PATTERNS)
        print(f"{repo_id}@{revision[:8]} -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
