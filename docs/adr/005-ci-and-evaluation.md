# ADR-005: Lightweight, reproducible CI; full evaluation runs locally

- **Status:** accepted (CI); evaluation section partly recorded, completed in phase 5
- **Date:** 2026-10-20

## Context
The pipeline depends on multi-GB models (bge-m3, bge-reranker) and paid LLM calls. Running them
on every push would be slow, costly and non-deterministic. CI still has to catch regressions in
parsing, citation validation, metrics and secrets.

## Decision

### CI scope
`.github/workflows/ci.yml` runs ruff (lint + format check), pytest (HTML fixtures, Qdrant
`:memory:`, fake embeddings, fake LLM) and gitleaks. It installs only the `dev` dependency group
(`uv sync --frozen`): no torch, no model downloads, no LLM calls. Smoke tests (`-m smoke`) are
excluded by default.

### Runner and action pinning
- `runs-on: ubuntu-24.04`, **pinned for reproducibility** instead of `ubuntu-latest`, which
  moves to a new Ubuntu release without a change in this repository (the migration to Ubuntu 26
  began on 2026-10-19). Moving the runner is an explicit commit.
- Actions are pinned to the latest major that runs on Node 24 (Node 20 is deprecated on
  GitHub-hosted runners): `actions/checkout@v7`, `astral-sh/setup-uv@v10.3.0` (the project
  publishes no floating major tag), `gitleaks/gitleaks-action@v3`.

### Artifacts
The only artifact is `gitleaks-results.sarif`, uploaded by gitleaks-action: the scan report
(rule list plus findings, with secrets redacted by `--redact`). It contains no repository files;
`.env` and `data/raw/` are not tracked, so they are never in the checkout.

## Alternatives considered
- `ubuntu-latest`: less maintenance, but the image changes under us.
- Running the evaluation in CI: needs models and API keys; rejected for cost and determinism.

## Consequences
- Runner and action upgrades are manual, deliberate commits.
- Evaluation reports are produced locally and committed (details in phase 5).

## Evaluation
The full design is recorded in phase 5. Decisions taken before it (2026-11-05):

- **Dataset.** Candidate questions are written by Claude Code from seeded samples and enter as
  drafts; only human-validated items count (ADR-007).
- **RAGAS stays TBD until there is Gemini quota.** The judge (`gemini-3.1-pro-preview`) returned
  HTTP 429 (quota exceeded) on the free tier, and the generator is capped at 20 requests a day.
  Faithfulness and answer relevancy, and the judge-human agreement, are reported as "TBD" until
  the judge can run. Retrieval metrics (recall@k and MRR, all ablations) need no LLM, and
  citation and abstention rates need only the generator.
- **Generator for the full pipeline: chosen at the start of phase 5.** The likely option is a
  local model served by llama.cpp through the existing `llm.provider: local` switch (ADR-006).
  The model, its GGUF file SHA-256, the quantization and the llama.cpp version will be pinned in
  config, like the Gemini IDs. Reports name the generator that produced them.
- **Hardware limits for local runs.** The machine is a laptop: Intel Core i7-10870H, 64 GB RAM,
  NVIDIA GeForce RTX 2070 Super with 8 GB VRAM. It overheats, so the GPU cannot run at full load
  for long periods. Local runs must use partial GPU offload or CPU, bounded batches with pauses,
  and caching so that a run can resume instead of repeating work. torch stays CPU-only
  (ADR-001); only the llama.cpp server would use the GPU.
