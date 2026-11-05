# ADR-007: Evaluation questions written by Claude Code from seeded samples

- **Status:** accepted
- **Date:** 2026-11-05

## Context
The plan had an LLM (Gemini, through the provider of ADR-006) draft 90 candidate questions in
3 batches of 30. In phase 3 the Gemini free tier proved too small: 20 requests a day for
`gemini-3.8-flash`, frequent 503s and responses of several minutes. The generator under test
would also be writing its own exam, which favors questions shaped like its own answers. The rule
that protects the dataset is not who writes the drafts but that only a human validates them.

## Decision
- **Author.** The candidates are written by Claude Code (Claude Opus 5.5) in a working session,
  following `prompts/draft_questions.md`. Each item records `generated_by:
  "claude-code/claude-opus-5-5"`, the `batch` and the `seed`.
- **Deterministic sampling stays in code.** `python -m eval.draft_questions brief --batch N`
  (`make draft-brief BATCH=N`) samples live norm units with a fixed seed (1000) and writes a
  brief to `eval/drafts/` (not versioned):
  - candidate pools: substantive units (120 or more characters) for `factual_single` and
    `unanswerable`; units with a deadline, amount or percentage for `deadline_or_value`; article
    capita whose text cites another article of the norm for `multi_article`, shown with the
    cited articles;
  - each category's slots are split across Títulos in proportion to the pool (largest
    remainder), and chapters are alternated inside each Título;
  - one article feeds at most one candidate across all categories and batches, so the batches
    are disjoint;
  - the brief lists twice the quota, so weak units (pure cross-references, figure-only content,
    past transitional dates) can be skipped.
- **Quotas.** 30 `factual_single`, 20 `multi_article`, 20 `deadline_or_value` and
  20 `unanswerable`, 30 per batch. The remainders of 20 / 3 rotate across categories, so the
  batches are 10/6/7/7, 10/7/6/7 and 10/7/7/6.
- **Draft-only ingestion.** `python -m eval.draft_questions add --batch N` (`make draft-add`)
  reads `eval/drafts/batch-N.jsonl`, accepts only the authoring fields (`question`, `category`,
  `expected_unit_ids`, `reference_answer`, `source_unit_id`, `notes`), and writes items with
  `status: draft` and `validated_by: null`. A row that tries to set status, IDs or provenance is
  refused (tested). It also checks the batch quota and the corpus rules before writing.
- **Schema and checks** (`eval/schema.py`, `make validate-dataset`, and a CI test against the
  versioned extract):
  - `validated` requires `validated_by`, and a draft cannot have one; `rejected` exists so a
    reviewer can discard an item without deleting its history;
  - `unanswerable` has no expected units and must explain why in `notes`; the other categories
    need units;
  - expected units exist, are not revoked and are not annex units (annexes are out of the MVP
    dataset, so the plan's rule for `deadline_or_value` covers every category);
  - `multi_article` spans at least two articles; `factual_single` and `deadline_or_value` stay in
    one;
  - IDs and normalized questions are unique.
- **Authoring rules** (in `prompts/draft_questions.md`): plain wording without article numbers;
  questions written from the brief only, never from retrieval output; expected units are the most
  specific complete set; `unanswerable` items are near misses checked against the full text.
- **Validation** follows `eval/VALIDATION_GUIDE.md`. Only `validated` items count in phase 5.

## Alternatives considered
- **Gemini as author, as planned.** Blocked by the quota, and it would favor the system under
  test.
- **A local model as author.** Weaker PT-BR legal reading on 8 GB of VRAM, and the same
  self-preference issue if it also generates the answers in phase 5.
- **Hand-written questions only.** Highest quality, but it moves 90 items of work to the
  reviewer; drafting plus validation keeps the human step focused on checking.

## Consequences
- The sample is reproducible from the seed; the wording is not (as with any LLM). The dataset
  file is the versioned artifact.
- Writing the unanswerable items surfaced facts the plan had wrong: "unidade consumidora" is
  defined (`art-2-inc-L`), so the near-miss candidate of decision 33 is answerable; the
  presential waiting time (Art. 380) and the MIGDI power limit (Art. 523) are also in the norm.
- The author knows the norm well, so some questions may be easier than a real user's. The
  reviewer should reject or rewrite items that only make sense to someone reading the article.
