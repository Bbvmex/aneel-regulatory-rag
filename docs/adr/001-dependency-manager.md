# ADR-001: uv as dependency and environment manager, Python 3.12

- **Status:** accepted
- **Date:** 2026-10-20

## Context
The project mixes a light core (parsing, Qdrant client, LangChain/LangGraph) with heavy, local-only
dependencies (PyTorch, FlagEmbedding, RAGAS, Gradio). CI must stay fast and must never download
models or CUDA wheels. The development machine runs Windows with a system Python 3.14, which is
too new for parts of the ML stack.

## Decision
- Use **uv** with a project-local `.venv` and a committed `uv.lock`.
- Pin **Python 3.12** via `.python-version` and `requires-python = ">=3.12,<3.13"`.
- Split dependencies into groups: `dev` (default, used by CI), `ml`, `eval`, `demo`.
- Resolve `torch` from the PyTorch **CPU** index (`explicit = true`), so no CUDA packages are ever
  pulled.

## Alternatives considered
- **Poetry:** mature, but slower resolution, and per-package custom indexes and Python download
  need extra tooling; uv handles both natively.
- **pip + venv + requirements.txt:** no lockfile with hashes across groups; easy to drift.

## Consequences
- `uv sync --frozen` in CI installs only `dev`; the lockfile still pins the heavy groups for local
  reproducibility.
- Contributors need uv installed; `make setup` wraps the commands.
