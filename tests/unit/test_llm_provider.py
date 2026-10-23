"""Provider switch by config, json_schema -> json_mode fallback and parse retries (no network)."""

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage
from pydantic import BaseModel

from aneel_rag.config import load_config
from aneel_rag.config.settings import Secrets
from aneel_rag.llm.factory import MissingEndpointError, get_chat_model, get_provider
from aneel_rag.llm.provider import ChatProvider, StructuredOutputError

SECRETS = Secrets(
    _env_file=None,
    llm_base_url="https://gemini.example/v1beta/openai/",
    llm_api_key="gemini-key",
    judge_base_url="https://judge.example/v1/",
    judge_api_key="judge-key",
    local_llm_base_url="http://localhost:8080/v1",
)


def _cfg(provider, generator):
    cfg = load_config()
    llm = cfg.llm.model_copy(update={"provider": provider})
    models = cfg.models.model_copy(update={"generator": generator})
    return cfg.model_copy(update={"llm": llm, "models": models})


@pytest.mark.parametrize(
    ("provider", "generator", "base_url"),
    [
        ("gemini", "gemini-3.8-flash", "https://gemini.example/v1beta/openai/"),
        ("local", "qwen3-8b-instruct-q4_k_m", "http://localhost:8080/v1"),
    ],
)
def test_provider_is_switched_by_config(provider, generator, base_url):
    chat = get_chat_model("generator", _cfg(provider, generator), SECRETS)
    assert chat.model_name == generator
    assert chat.openai_api_base == base_url
    assert chat.temperature == 0


def test_default_config_uses_the_pinned_gemini_generator():
    chat = get_chat_model("generator", load_config(), SECRETS)
    assert (chat.model_name, chat.openai_api_base) == ("gemini-3.8-flash", SECRETS.llm_base_url)


def test_judge_keeps_its_endpoint_when_the_generator_goes_local():
    chat = get_chat_model("judge", _cfg("local", "qwen"), SECRETS)
    assert (chat.model_name, chat.openai_api_base) == (
        "gemini-3.1-pro-preview",
        SECRETS.judge_base_url,
    )


def test_missing_key_fails_clearly():
    with pytest.raises(MissingEndpointError, match=r"fill \.env"):
        get_chat_model("generator", load_config(), Secrets(_env_file=None, llm_base_url="x"))


def test_get_provider_reads_structured_output_settings():
    provider = get_provider("generator", load_config(), SECRETS)
    assert (provider.method, provider.max_parse_retries) == ("json_schema", 1)


class Reply(BaseModel):
    value: int


class StubChat:
    """Stands in for ChatOpenAI.with_structured_output(..., include_raw=True)."""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.methods: list[str] = []
        self.inputs: list[list] = []

    def with_structured_output(self, schema, method, include_raw):
        assert include_raw
        self.methods.append(method)
        return self

    def invoke(self, messages):
        self.inputs.append(messages)
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def _ok(value):
    return {"raw": AIMessage(content=f'{{"value": {value}}}'), "parsed": Reply(value=value)}


def _bad(error="value: field required"):
    return {"raw": AIMessage(content="{}"), "parsed": None, "parsing_error": error}


def _rejected():
    request = httpx.Request("POST", "https://x/chat/completions")
    return openai.BadRequestError(
        "response_format not supported", response=httpx.Response(400, request=request), body=None
    )


def test_json_schema_rejection_falls_back_to_json_mode():
    chat = StubChat([_rejected(), _ok(7)])
    provider = ChatProvider(chat, "m")
    assert provider.structured("sys", "user", Reply) == Reply(value=7)
    assert chat.methods == ["json_schema", "json_mode"]
    assert provider.method == "json_mode"  # sticky: later calls skip json_schema
    assert "JSON Schema" in chat.inputs[-1][0].content


def test_parse_error_is_retried_with_feedback():
    chat = StubChat([_bad(), _ok(3)])
    assert ChatProvider(chat, "m", max_parse_retries=1).structured("s", "u", Reply).value == 3
    retry = chat.inputs[1]
    assert len(retry) == 4
    assert "did not match the schema: value: field required" in retry[-1].content


def test_parse_errors_beyond_the_budget_raise():
    chat = StubChat([_bad(), _bad()])
    with pytest.raises(StructuredOutputError, match="no valid Reply"):
        ChatProvider(chat, "m", max_parse_retries=1).structured("s", "u", Reply)
