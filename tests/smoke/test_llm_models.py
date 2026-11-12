import httpx
import pytest

from aneel_rag.config import get_secrets, load_config
from aneel_rag.llm.factory import endpoint

pytestmark = pytest.mark.smoke


def _list_model_ids(base_url: str, api_key: str) -> set[str]:
    resp = httpx.get(
        base_url.rstrip("/") + "/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    resp.raise_for_status()
    # Gemini's OpenAI-compatible endpoint prefixes IDs with "models/".
    return {m["id"].removeprefix("models/") for m in resp.json()["data"]}


@pytest.mark.parametrize("role", ["generator", "judge"])
def test_configured_model_exists(role):
    # With llm.provider: local, `make llm-server` serves the GGUF under the generator ID.
    cfg = load_config()
    base_url, api_key = endpoint(role, cfg, get_secrets())
    if not (base_url and api_key):
        pytest.skip(f"no endpoint/key configured for {role}")

    model_id = getattr(cfg.models, role)
    available = _list_model_ids(base_url, api_key)
    assert model_id in available, f"{role} model '{model_id}' not served by {base_url}"
