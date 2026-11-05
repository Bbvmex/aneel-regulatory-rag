"""Structured-output LLM calls behind a small protocol (ADR-006)."""

import json
import logging
from typing import Any, Literal, Protocol, TypeVar

import openai
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)
Method = Literal["json_schema", "json_mode"]

log = logging.getLogger(__name__)


class StructuredOutputError(RuntimeError):
    """The model kept replying with JSON that does not match the schema."""


class LLMProvider(Protocol):
    model_id: str

    def structured(self, system: str, user: str, schema: type[T]) -> T: ...


class ChatProvider:
    """OpenAI-compatible chat model returning validated Pydantic objects.

    Parse retries live here, apart from the citation retry of the graph.
    """

    def __init__(
        self,
        chat: BaseChatModel,
        model_id: str,
        method: Method = "json_schema",
        max_parse_retries: int = 1,
    ):
        self.chat = chat
        self.model_id = model_id
        self.method = method
        self.max_parse_retries = max_parse_retries

    def structured(self, system: str, user: str, schema: type[T]) -> T:
        if self.method == "json_schema":
            try:
                return self._call(system, user, schema)
            except openai.BadRequestError as exc:
                # Some OpenAI-compatible servers reject response_format=json_schema.
                log.warning("%s rejected json_schema (%s); using json_mode", self.model_id, exc)
                self.method = "json_mode"
        return self._call(system, user, schema)

    def _call(self, system: str, user: str, schema: type[T]) -> T:
        if self.method == "json_mode":
            # json_mode only promises JSON, so the schema has to travel in the prompt.
            shape = json.dumps(schema.model_json_schema(), ensure_ascii=False)
            system = f"{system}\n\nReply with one JSON object matching this JSON Schema:\n{shape}"
        runnable = self.chat.with_structured_output(schema, method=self.method, include_raw=True)
        messages: list[BaseMessage] = [SystemMessage(system), HumanMessage(user)]
        for _ in range(self.max_parse_retries + 1):
            out: dict[str, Any] = runnable.invoke(messages)
            if isinstance(out.get("parsed"), schema):
                return out["parsed"]
            error = out.get("parsing_error") or "no JSON object in the reply"
            messages = [
                *messages,
                out["raw"],
                HumanMessage(
                    f"The reply did not match the schema: {error}. "
                    "Reply again with only the corrected JSON object."
                ),
            ]
        raise StructuredOutputError(f"{self.model_id}: no valid {schema.__name__} ({error})")


class ScriptedProvider:
    """Replays queued replies per schema, for tests; no network."""

    model_id = "scripted"

    def __init__(self, replies: dict[type[BaseModel], list[BaseModel | dict]]):
        self.replies = {schema: list(queue) for schema, queue in replies.items()}
        self.calls: list[tuple[str, str, type[BaseModel]]] = []

    def structured(self, system: str, user: str, schema: type[T]) -> T:
        self.calls.append((system, user, schema))
        reply = self.replies[schema].pop(0)
        return reply if isinstance(reply, schema) else schema.model_validate(reply)
