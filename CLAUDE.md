# CLAUDE.md — permanent rules for aneel-regulatory-rag

The full approved plan and its current status live in [docs/PLAN.md](docs/PLAN.md). Read its
**Status** section first: the decisions recorded there override the original plan text.

## Workflow
- **Direct execution.** Work happens in this session; the Tonho/Bob/Edna/Wan agent cycle is
  not used (D11). A reviewer pass (Edna) runs only when the user asks for one.
- **One phase at a time.** Implement only the phase the user authorized, then stop for review.
  Do not start the next phase until the user says so.
- **Branch and PR pattern.** Phases use a `phase-N` branch; other work uses `chore/<topic>`,
  `fix/<topic>` and so on. Push the branch and open the PR with `gh pr create --body-file`,
  following `.github/pull_request_template.md` (Summary, Files, Acceptance criteria with
  checkboxes, How to verify, Out of scope). Add "Decisions not in the plan" when something
  diverged. CI must be green before handing the PR over.
- **Never merge.** Never merge a PR, push to `main` or delete remote branches. The user reviews
  and merges.
- **PR comments are the channel for review.** All review requests, questions and decisions go
  through PR comments, in English. Reply on the PR (`gh pr comment`), not only in the terminal.
  Terminal chat is for operational commands only.
- After every merged phase, update the **Status** section of `docs/PLAN.md`.

## Data and evaluation (do not change without an explicit request)
- **Never edit `eval/thresholds.yaml` or `eval/dataset.jsonl`** (or `eval/judge_calibration.jsonl`)
  unless the user asks for that specific change.
- LLM-generated questions enter as `status: draft` and **do not count** in metrics. Only the user
  marks an item `status: validated`.
- Candidate questions are written by Claude Code from the seeded briefs of
  `eval/draft_questions.py`, following `prompts/draft_questions.md` (ADR-007). They are added only
  through `make draft-add`, which writes drafts; never write `validated` or `validated_by`.
- RAGAS metrics (faithfulness, answer relevancy) and judge-human agreement stay **TBD** until there
  is Gemini quota for the judge (ADR-005).
- **No metric, percentage or performance number** may appear in the README, docs or commits
  unless a report in `eval/reports/` (with date, git SHA and config hash) produced it. Without a
  report, write "TBD".

## Configuration
- **Every parameter that affects results lives in `config/*.yaml`**: models, k values, chunking,
  temperature, quote limits and prompts.
- **`.env` holds only secrets and endpoints.** `.env.example` is committed. Never hardcode
  secrets, and never read or commit `.env`.
- Model IDs are pinned: generator `gemini-3.8-flash`, judge `gemini-3.1-pro-preview`.
  **`-latest` aliases are forbidden**, and `settings.py` rejects them.
- The phase 5 generator is chosen with the user at the start of phase 5 (likely local, llama.cpp
  through `llm.provider: local`). A local model is pinned like the others: GGUF SHA-256,
  quantization and llama.cpp version in config.

## Local hardware
- Laptop: Intel Core i7-10870H, 64 GB RAM, NVIDIA RTX 2070 Super (8 GB VRAM). It overheats:
  **never keep the GPU at full load for long periods.** Use partial GPU offload or CPU, bounded
  batches with pauses, and caches so that long runs can resume. torch stays CPU-only (ADR-001).

## Corpus
- The source is the compiled text of REN ANEEL nº 1.000/2021 on leis.org, ANEEL's official
  legislation platform. Never call it a "portal consolidador".
- Only `data/raw/ren1000_law_content.html` and `data/raw/SOURCE.md` are versioned. The full HTML
  and the PDF stay out of git, and ingestion runs from the extract.
- No client, company or real-case data, only the public text of the norm.

## Language and style
- Code, README, docstrings and ADRs are in English. The corpus and the evaluation questions are in
  PT-BR. Planning documents (`docs/PLAN.md`) are in PT-BR.
- The README states that this is a personal project with no relation to any employer or client.
- Lint and tests: `make lint`, `make test`. Pre-commit (ruff, gitleaks) must pass, and hooks are
  never skipped.
