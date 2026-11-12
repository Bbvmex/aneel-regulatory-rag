# ADR-006: LLM provider behind one OpenAI-compatible interface

- **Status:** accepted
- **Date:** 2026-10-23

## Context
The generator is Gemini today, and phase 8 compares it with a local llama.cpp server. Both expose
an OpenAI-compatible chat API. The graph needs structured output (a context grade and an answer
with citations), and OpenAI-compatible servers differ in what `response_format` they accept. The
judge for phase 5 must stay fixed while the generator changes, or the comparison would be void.

## Decision
- **Factory.** `llm/factory.py` has `get_chat_model(role, cfg)`, with `role` either `generator`
  or `judge`, returning `ChatOpenAI(model, base_url, api_key, temperature, timeout, max_retries)`.
  The model ID comes from `config/*.yaml` (`models.generator`, `models.judge`); endpoints and keys
  come from `.env` only.
- **Provider switch.** `llm.provider` (`gemini | local`) selects the generator endpoint:
  `LLM_BASE_URL` and `LLM_API_KEY`, or `LOCAL_LLM_BASE_URL` with a placeholder key, since
  llama.cpp ignores it but the client requires one. The judge always uses `JUDGE_BASE_URL` and
  `JUDGE_API_KEY`, whatever the provider. A missing endpoint or key fails with a message pointing
  to `.env.example`.
- **Protocol.** The graph depends on `LLMProvider.structured(system, user, schema) -> schema`,
  not on LangChain. `ChatProvider` implements it over a chat model; `ScriptedProvider` replays
  queued replies, for tests only (it is not selectable through config).
- **Structured output.** `llm.structured_output: json_schema` sends the Pydantic schema as
  `response_format`. If the server rejects it with HTTP 400, the provider switches to `json_mode`
  for the rest of the run, putting the JSON Schema in the system prompt. Either way the reply is
  validated with Pydantic. An invalid reply is sent back with the parse error, up to
  `llm.max_parse_retries` (1) times, then `StructuredOutputError` is raised. These parse retries
  are separate from the citation retry of the graph (ADR-004).
- **Transient errors.** HTTP 429 and 5xx are retried by the OpenAI client with exponential
  backoff, `llm.max_retries` (3) times. The CLI reports a remaining failure as an error and does
  not turn it into an abstention: an abstention means the norm does not answer the question, not
  that the API was down.
- **Models.** The generator is `gemini-3.8-flash` (GA, fixed ID), also used by `grade_context` in
  the MVP. The judge is `gemini-3.1-pro-preview`. There is no current stable Pro model, so a
  preview is the only option at that tier. Risk: a preview ID can change behavior or be withdrawn.
  Mitigations: the judge cache is keyed by `judge_model_id`, the judge is calibrated against human
  labels, the ID is written in every report, and `make smoke` fails when the endpoint no longer
  serves a configured model. **`-latest` aliases are forbidden**: `settings.py` rejects any
  generator or judge ID ending in `-latest` (tested).
- **Temperature** is `generation.temperature` (0) for both roles.

## Alternatives considered
- **Google's native SDK.** Better feature coverage for Gemini, but llama.cpp would need a second
  code path, and the comparison in phase 8 would test two integrations instead of two models.
- **Function calling for structured output.** It works on both servers, but `json_schema` is the
  most direct contract; function calling stays available as a later fallback if needed.
- **LangChain's `with_structured_output` straight in the nodes.** It would tie the graph tests to
  LangChain internals; the protocol keeps the nodes testable with a plain fake.

## Consequences
- Switching to llama.cpp is a config change (`llm.provider: local` and `models.generator`), which
  phase 8 will put in `config/providers/local.yaml`.
- The `json_mode` fallback is sticky per provider instance, so a server that rejects
  `json_schema` costs one failed request per run.
- The Gemini free tier can return 503 ("high demand") or 429 (quota) even after retries; local
  runs then fail with a clear error and must be repeated.
