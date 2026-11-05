"""Chat models per role; Gemini and llama.cpp differ only in config and .env (ADR-006)."""

from typing import Literal

from langchain_openai import ChatOpenAI

from aneel_rag.config.settings import AppConfig, Secrets, get_secrets
from aneel_rag.llm.provider import ChatProvider

Role = Literal["generator", "judge"]

# llama.cpp ignores the key, but the OpenAI client refuses to start without one.
LOCAL_API_KEY = "local"


class MissingEndpointError(RuntimeError):
    pass


def endpoint(role: Role, cfg: AppConfig, secrets: Secrets) -> tuple[str, str]:
    """(base_url, api_key); llm.provider switches the generator, the judge stays apart."""
    if role == "judge":
        return secrets.judge_base_url, secrets.judge_api_key
    if cfg.llm.provider == "local":
        return secrets.local_llm_base_url, LOCAL_API_KEY
    return secrets.llm_base_url, secrets.llm_api_key


def get_chat_model(role: Role, cfg: AppConfig, secrets: Secrets | None = None) -> ChatOpenAI:
    base_url, api_key = endpoint(role, cfg, secrets or get_secrets())
    if not (base_url and api_key):
        raise MissingEndpointError(
            f"no endpoint or API key for the {role} ({cfg.llm.provider}); "
            "fill .env from .env.example"
        )
    return ChatOpenAI(
        model=getattr(cfg.models, role),
        base_url=base_url,
        api_key=api_key,
        temperature=cfg.generation.temperature,
        timeout=cfg.llm.timeout_s,
        max_retries=cfg.llm.max_retries,
    )


def get_provider(role: Role, cfg: AppConfig, secrets: Secrets | None = None) -> ChatProvider:
    return ChatProvider(
        get_chat_model(role, cfg, secrets),
        getattr(cfg.models, role),
        cfg.llm.structured_output,
        cfg.llm.max_parse_retries,
    )
