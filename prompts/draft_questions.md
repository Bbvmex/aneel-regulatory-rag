Rules for writing evaluation questions about ANEEL Normative Resolution No. 1,000/2021 from a
batch brief (`eval/drafts/batch-N-brief.md`). The author is Claude Code (ADR-007). The output is
`eval/drafts/batch-N.jsonl`, one JSON object per line with exactly these fields:
`question`, `category`, `expected_unit_ids`, `reference_answer`, `source_unit_id`, `notes`.
Status, IDs and provenance are added by `eval.draft_questions add`; every item enters as draft.

General
- Write the question in Brazilian Portuguese, the way a consumer, a utility analyst or a lawyer
  would ask it. Use plain wording, not the article's sentence turned into a question, so lexical
  overlap alone does not solve retrieval. Do not mention article numbers in the question.
- One clear question per item. It must have a single correct answer in the norm (or none, for
  `unanswerable`).
- Write the questions from the brief only, without looking at retrieval results, so the dataset
  is not tuned to the system under test.
- `source_unit_id` is the brief candidate the question came from.
- `expected_unit_ids` lists the most specific units that hold the answer (an inciso, not its
  article, when the inciso has it), and all of them when the answer needs several. Do not list
  units that only give context.
- `reference_answer` is a short answer in PT-BR, true to the text, that a reviewer can check
  against the expected units.
- Skip candidates that are pure cross-references, definitions without content, transitional
  dates that are already past, or text whose meaning depends on a figure or formula.

Categories
- `factual_single`: the answer is in one article (one or more of its units). Who, what, when,
  under what condition, whether something is allowed or required.
- `multi_article`: the answer needs units from at least two articles, for example a rule and its
  exception, a procedure and its deadline, or two obligations combined. Say in `notes` why each
  article is needed.
- `deadline_or_value`: the answer is a deadline, period, amount, percentage or limit, cited in the
  article's own device. Never point to the deadline table after Art. 679 or to any annex. The
  units must be in one article.
- `unanswerable`: a near miss. Start from the candidate's topic and ask a neighboring question
  that a real user could ask and that REN 1.000/2021 does not answer (a value set by another
  norm, a detail the norm leaves to the utility, a case it does not regulate). Never absurd and
  never off-topic. `expected_unit_ids` is empty. `notes` names the source unit and says why the
  norm does not answer; check the full text (search `data/processed/units.jsonl`) before saying
  so.
