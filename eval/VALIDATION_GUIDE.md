# Validating the evaluation dataset

`eval/dataset.jsonl` holds 90 candidate questions about REN 1.000/2021, written by Claude Code
from seeded samples of the norm (ADR-007). Every item starts as `status: draft`. **Drafts never
count in metrics.** Phase 5 evaluates only `validated` items and warns when there are fewer than
50.

Only a human marks an item `validated`. Tools may create drafts; nothing in the code writes
`validated`.

## How to review an item

Open the item, then the units in `expected_unit_ids` (search `data/processed/units.jsonl`, or
open the `source_url` of each unit). Check:

1. **The question is natural.** A consumer, a utility analyst or a lawyer could ask it. It does
   not copy the article's sentence and does not cite article numbers.
2. **The answer is in the norm, and only there.** `reference_answer` is true to the text of the
   expected units, with no outside knowledge.
3. **The expected units are the most specific and complete set.** Each unit holds part of the
   answer. Point to the inciso or alínea, not to its article, when the inciso has the answer. No
   unit that holds part of the answer is missing.
4. **The category is right:**
   - `factual_single`: units from one article;
   - `multi_article`: units from at least two articles, each one needed (see `notes`);
   - `deadline_or_value`: the answer is a deadline, period, amount, percentage or limit, and
     the units point **to the device in the article, never to the deadline table after
     Art. 679 or to any annex** (`validate_dataset` rejects annex units);
   - `unanswerable`: a near miss. Check that the norm really does not answer it (search the
     units for the key terms) and that the question is **never absurd**: it stays in the norm's
     subject, close to what the norm does regulate. `notes` names the source unit and why the
     norm does not answer.
5. **There is a single correct answer.** Ambiguous questions are rejected or rewritten.

## How to record the decision

Edit the line in `eval/dataset.jsonl`:

- accept: `"status": "validated", "validated_by": "<your name>"`;
- reject: `"status": "rejected", "validated_by": "<your name>"`, with the reason in `notes`;
- fix and accept: edit `question`, `expected_unit_ids`, `reference_answer` or `notes`, then
  mark it validated.

Do not change `id`, `batch`, `seed`, `generated_by` or `source_unit_id`: they record provenance.

Then run:

```bash
make validate-dataset   # schema, unit IDs against the parsed corpus, counts by status
make test               # includes the same checks against the versioned extract
```

## Known points to look at

- Some `deadline_or_value` items were sampled as `factual_single` or `unanswerable` candidates
  and moved because their answer is a value; `notes` says so.
- Some `unanswerable` items are deliberate near misses where a related device exists (for
  example DIC limits without the compensation amount); the related device is named in `notes`.
