# ADR-005: Lightweight, reproducible CI; full evaluation runs locally

- **Status:** accepted (CI 2026-10-20; evaluation 2026-11-12)
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

### Phase 5 design (2026-11-12)
- **What counts.** Only `validated` items; drafts and rejected items are counted in the report
  and ignored. Retrieval metrics use the answerable items.
- **Retrieval metrics, per ablation, no LLM.** Recall@k (k = 1, 3, 5) and MRR at article level
  (main: the expected units' articles against each chunk's `article_ids`) and at unit level
  (expected units against each chunk's body `unit_ids`, never `context_unit_ids`). Variants
  with a reranker also report the recall of the candidate pool at `k_candidates`, the ceiling
  of decision 25. Slices: per category and the Art. 2 definitions (decisions 27 and 30). The
  dataset has no paraphrase tag, so decision 29 is read from the category rows.
- **Ablations are config overlays.** `config/ablations/*.yaml` override only the keys they set
  (`load_config(overlays=...)`); `config/eval.yaml` lists them, with the recall k values, the GPU
  pauses, the judge settings and the calibration sample. Beyond the four of the plan, two cover
  decision 26c: the reranker truncated at 512 tokens and 10 reranker candidates. 1024 tokens is
  not run, because no (question, chunk) pair passes 1024 tokens (decision 49). The fixed-chunking
  variant needs its own collection (`make index OVERLAY=config/ablations/fixed_chunking.yaml`).
  The embedder is loaded once per run, and one reranker per truncation length (decision 32).
- **Full graph, main config only.** Abstention accuracy (unanswerable items that abstained),
  false abstention rate (answerable items that abstained), the share of answerable items
  answered citing an expected unit or one of its ancestors or descendants, and the rates of
  `valid`, `imprecise` and `invalid` over the citations of each question's last attempt (so a
  rejected answer's invalid citations count). The runner starts its own `llama-server` through
  the pin check of ADR-008, and refuses to run if one is already serving. Answers are cached in
  `data/cache/eval/<config hash>/`, keyed by the question, with the git SHA that produced them;
  an interrupted run resumes, and failed questions are retried on the next run. Between
  questions it pauses and waits for the GPU to cool.
- **RAGAS on request (`--judge`).** Faithfulness and answer relevancy from `ragas` 0.4
  (`metrics.collections`), with the pinned judge through the `JUDGE_*` endpoint and the local
  bge-m3 dense vectors as the relevancy embeddings. Each judgement is a file
  `data/cache/judge/<sha256>.json`, keyed by (question, answer, contexts, judge model); the
  report shows the cache directory, hits, new calls and a hash of the keys used. Without quota
  the report says TBD.
- **Judge calibration.** `make calibration` samples 20 answered questions of the latest full
  report into `eval/judge_calibration.jsonl` as drafts with `faithful: null`; it never
  overwrites the file. With validated labels and `--judge`, the report shows accuracy and
  Cohen's kappa between the judge (faithful when the RAGAS faithfulness reaches
  `judge.faithful_threshold`, 1.0: every claim supported, the same definition as the human
  label) and the human, with the N.
- **Reports and gate.** `eval/reports/<date>_<git sha>_<config hash>.{md,json}` (a run that
  skips a part gets `_partial`). The JSON has flat `gate_metrics`; `eval/thresholds.yaml` maps
  their names to `min`/`max`. `make eval-gate` reads the newest full report of the current config
  hash and fails while the thresholds are empty, when a gated metric is TBD, or when one misses.
