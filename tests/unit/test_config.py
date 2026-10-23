import pytest
import yaml
from pydantic import ValidationError

from aneel_rag.config import AppConfig, config_hash, load_config
from aneel_rag.config.settings import DEFAULT_CONFIG


def _raw() -> dict:
    with open(DEFAULT_CONFIG, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_default_config_loads():
    cfg = load_config()
    assert cfg.retrieval.mode in {"dense", "sparse", "hybrid", "hybrid+rerank"}
    assert cfg.citations.min_quote_chars < cfg.citations.max_quote_chars


@pytest.mark.parametrize("role", ["generator", "judge"])
def test_latest_alias_rejected(role):
    raw = _raw()
    raw["models"][role] = "gemini-flash-latest"
    with pytest.raises(ValidationError, match="not allowed"):
        AppConfig.model_validate(raw)


@pytest.mark.parametrize("field", ["embedding_revision", "reranker_revision"])
@pytest.mark.parametrize("value", ["main", "5617a9f6", "v1.0"])
def test_hub_revision_must_be_a_commit_hash(field, value):
    raw = _raw()
    raw["models"][field] = value
    with pytest.raises(ValidationError, match="commit hash"):
        AppConfig.model_validate(raw)


def test_unknown_key_rejected():
    raw = _raw()
    raw["retrieval"]["k_typo"] = 3
    with pytest.raises(ValidationError):
        AppConfig.model_validate(raw)


def test_config_hash_is_stable_and_sensitive():
    raw = _raw()
    base = config_hash(AppConfig.model_validate(raw))
    assert base == config_hash(AppConfig.model_validate(_raw()))
    raw["retrieval"]["k_final"] += 1
    assert config_hash(AppConfig.model_validate(raw)) != base
