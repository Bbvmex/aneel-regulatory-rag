# ADR-004: Deterministic citation validation and abstention

- **Status:** accepted
- **Date:** 2026-10-23

## Context
The point of the project is that every answer is traceable to the device of REN 1.000/2021 it
comes from. An LLM asked to cite will sometimes paraphrase the "quote", cite a unit it never saw,
or cite the whole article for a sentence that lives in one of its incisos. Asking another LLM
whether a citation is right would be slow, costly and itself unverifiable. When the excerpts do
not answer the question, the system must say so, not guess.

## Decision
- **Graph** (LangGraph): `retrieve -> rerank -> grade_context -> (generate | abstain)`, then
  `generate -> validate_citations -> (END | generate | abstain)`. `retrieve` returns the candidate
  pool (`k_candidates` in `hybrid+rerank`) and `rerank` cuts it to the `k_final` hits shown to
  the LLM. Both reuse the phase 2 `Retriever`.
- **Context shown to the LLM** is one block per hit with each unit on its own line, prefixed by
  its ID (`[art-23-p1-inc-II] ...`): the repeated context units (caput, parent § or inciso) first,
  then the body units. Revoked units, if included, are marked.
- **Citable units** are the `unit_ids` and `context_unit_ids` of the hits shown (decision 24 of
  the plan status). A unit that exists but was not shown is out of context.
- **Policy D6**, checked in `graph/citations.py` for each citation, in this order:
  1. the `unit_id` exists in `units.jsonl`;
  2. it is in the citable units;
  3. the normalized quote has 20 to 300 characters (`citations.min_quote_chars` and
     `max_quote_chars`, inclusive);
  4. the normalized quote is a substring of the normalized unit text: **valid**;
  5. otherwise, if it is a substring of a descendant's text (an article cited for a § or inciso
     passage, or a § for an alínea): **imprecise**, accepted, with the descendant recorded in
     `matched_unit_id`;
  6. otherwise **invalid**. The reason names the in-context unit that does hold the quote, when
     one does, so the retry can fix the ID.
- **Normalization** applies to both sides: NFKC, casefold, typographic quotes and apostrophes
  unified to `"`, dashes and the minus sign unified to `-`, whitespace collapsed. A wrapping pair
  of quote marks and a leading or trailing ellipsis are dropped from the quote. An ellipsis in the
  middle is kept, so a quote that skips text is invalid.
- **Answer outcome.** An answer passes when it does not abstain, has at least one citation and no
  citation is invalid; imprecise citations pass and are reported as such. The empty-citations
  rule lives in the validator, not in the Pydantic schema, so it goes through the citation retry
  with an explicit error instead of the JSON parse retry.
- **Retry.** A failed validation sends the question, the context, the rejected answer and the list
  of errors back to `generate`, up to `generation.max_citation_retries` (1) times. After that the
  graph abstains. A model that abstains by itself is not retried.
- **Abstention.** `grade_context` asks the generator model (`ContextGrade{sufficient, reason}`)
  whether the excerpts answer the question. The reranker score is never used as an abstention
  threshold, because it saturates near the maximum on some queries (decision 31). An empty
  retrieval abstains without an LLM call. The `abstain` node returns `abstention.message` and the
  `abstention.n_snippets` (3) closest hits, plus a reason: `no_results`, `insufficient_context`,
  `model_abstained` or `citations`.
- **Prompts** live in `prompts/` and are listed in `config.prompts`. Their contents, together
  with the corpus SHA-256, are part of `config_hash`, so editing a prompt changes the hash that
  reports will carry.

## Alternatives considered
- **LLM-as-judge for citations.** Costly, non-deterministic, and it moves the problem instead of
  solving it. Deterministic checks are exact and run in CI.
- **Fuzzy matching (edit distance) for quotes.** It would accept small paraphrases, which is the
  failure being guarded against. Normalization covers the legitimate differences (typography,
  spacing, case).
- **Dropping invalid citations and keeping the rest.** It would hide model errors and could leave
  a statement without support. Failing the answer and retrying with the errors is stricter and
  measurable.
- **Rejecting article-level citations of § text outright.** The quote is real text of the cited
  article, so the answer is still traceable; flagging it as `imprecise` keeps it and lets the
  phase 5 report count it.

## Consequences
- Citation quality becomes three rates (valid, imprecise, invalid) that phase 5 can measure
  without a judge.
- A quote spanning two units (the end of a caput and the start of a §) is invalid by design.
- A revoked unit can only be cited when revoked units were included in retrieval; the validator
  does not treat it specially.
- Validation needs the unit texts, so the graph loads `data/processed/units.jsonl` and checks that
  it matches the current extract and parser before running.
