"""Model loading never reaches the Hub; a cache miss is a clear error (needs the ml group)."""

import pytest

pytest.importorskip("huggingface_hub")

from aneel_rag.retrieval.hub import ModelNotCachedError, local_model_path


def test_missing_model_raises_a_clear_error(tmp_path):
    with pytest.raises(ModelNotCachedError, match="make models"):
        local_model_path("BAAI/bge-m3", "0" * 40, cache_dir=tmp_path)
