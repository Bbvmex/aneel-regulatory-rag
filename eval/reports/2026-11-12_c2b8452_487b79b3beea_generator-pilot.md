# Generator pilot, 2026-11-12

- git `c2b8452`, config hash `487b79b3beea`, corpus sha256 `4c0dbc7f6f25…`
- llama.cpp `b12110`; retrieval `hybrid+rerank`
- 12 validated questions (3 per category, seed 20261112) of 90 validated; 0 drafts ignored
- questions: q-007, q-066, q-037, q-041, q-047, q-042, q-084, q-020, q-048, q-060, q-058, q-029

A pilot to choose the generator (ADR-008), one run per candidate: it is not an evaluation and its numbers do not measure the system.

| Candidate | Quant | Answered citing expected | All citations valid | False abstentions | Unanswerable abstained | Bracketed IDs | Retried | Errors | Gen tok/s | Prompt tok/s | Median s/question | Max GPU °C |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen3.6-35b-a3b | UD-Q4_K_M | 9/9 | 9/9 | 0 | 3/3 | 0 | 1 | 0 | 29.3 | 233.0 | 44.8 | 84 |
| qwen3.5-9b | Q5_K_M | 8/9 | 9/9 | 0 | 3/3 | 0 | 0 | 0 | 24.0 | 548.8 | 21.4 | 84 |
| gemma4-26b-a4b | Q4_0 (QAT) | 9/9 | 9/9 | 0 | 3/3 | 0 | 0 | 0 | 22.8 | 275.7 | 29.1 | 82 |
| gemma4-12b | Q4_0 (QAT) | 9/9 | 9/9 | 0 | 2/3 | 0 | 0 | 0 | 7.7 | 315.6 | 47.9 | 75 |

Seconds per question include retrieval and the CPU reranker (decision 26).

## Per question

### qwen3.6-35b-a3b

| ID | Category | Abstained | Reason | Attempts | Verdicts | Cited |
|---|---|---|---|---|---|---|
| q-007 | factual_single | False |  | 1 | valid | art-207-inc-IV-al-b |
| q-066 | factual_single | False |  | 1 | valid | art-560 |
| q-037 | factual_single | False |  | 1 | valid | art-328-p2 |
| q-041 | multi_article | False |  | 2 | valid, valid, valid | art-325-p6, art-422-inc-II, art-325-p5 |
| q-047 | multi_article | False |  | 1 | valid, valid | art-663-inc-I, art-663 |
| q-042 | multi_article | False |  | 1 | valid, valid | art-250, art-252-inc-II |
| q-084 | deadline_or_value | False |  | 1 | valid | art-276 |
| q-020 | deadline_or_value | False |  | 1 | valid | art-651 |
| q-048 | deadline_or_value | False |  | 1 | valid | art-365-p2 |
| q-060 | unanswerable | True | insufficient_context | 0 |  |  |
| q-058 | unanswerable | True | insufficient_context | 0 |  |  |
| q-029 | unanswerable | True | insufficient_context | 0 |  |  |

### qwen3.5-9b

| ID | Category | Abstained | Reason | Attempts | Verdicts | Cited |
|---|---|---|---|---|---|---|
| q-007 | factual_single | False |  | 1 | valid | art-207-inc-IV-al-b |
| q-066 | factual_single | False |  | 1 | valid | art-560 |
| q-037 | factual_single | False |  | 1 | valid, valid | art-328-p2, art-328-p1 |
| q-041 | multi_article | False |  | 1 | valid, valid, valid | art-325-p6, art-422-inc-II, art-325-p5 |
| q-047 | multi_article | False |  | 1 | valid, valid | art-663, art-663-inc-I |
| q-042 | multi_article | False |  | 1 | valid, valid | art-250, art-252-inc-II |
| q-084 | deadline_or_value | False |  | 1 | valid | art-276 |
| q-020 | deadline_or_value | False |  | 1 | valid, valid | art-651, art-102-inc-II |
| q-048 | deadline_or_value | False |  | 1 | valid | art-369 |
| q-060 | unanswerable | True | insufficient_context | 0 |  |  |
| q-058 | unanswerable | True | insufficient_context | 0 |  |  |
| q-029 | unanswerable | True | insufficient_context | 0 |  |  |

### gemma4-26b-a4b

| ID | Category | Abstained | Reason | Attempts | Verdicts | Cited |
|---|---|---|---|---|---|---|
| q-007 | factual_single | False |  | 1 | valid | art-207-inc-IV-al-b |
| q-066 | factual_single | False |  | 1 | valid | art-560 |
| q-037 | factual_single | False |  | 1 | valid | art-328-p2 |
| q-041 | multi_article | False |  | 1 | valid, valid, valid | art-422-inc-II, art-325-p6, art-325-p5 |
| q-047 | multi_article | False |  | 1 | valid, valid | art-663-inc-I, art-663 |
| q-042 | multi_article | False |  | 1 | valid, valid | art-250, art-252-inc-II |
| q-084 | deadline_or_value | False |  | 1 | valid | art-276 |
| q-020 | deadline_or_value | False |  | 1 | valid | art-651 |
| q-048 | deadline_or_value | False |  | 1 | valid | art-365-p2 |
| q-060 | unanswerable | True | insufficient_context | 0 |  |  |
| q-058 | unanswerable | True | insufficient_context | 0 |  |  |
| q-029 | unanswerable | True | insufficient_context | 0 |  |  |

### gemma4-12b

| ID | Category | Abstained | Reason | Attempts | Verdicts | Cited |
|---|---|---|---|---|---|---|
| q-007 | factual_single | False |  | 1 | valid | art-207-inc-IV-al-b |
| q-066 | factual_single | False |  | 1 | valid | art-560 |
| q-037 | factual_single | False |  | 1 | valid | art-328-p2 |
| q-041 | multi_article | False |  | 1 | valid, valid, valid | art-422-inc-II, art-325-p5, art-325-p6 |
| q-047 | multi_article | False |  | 1 | valid | art-663-inc-I |
| q-042 | multi_article | False |  | 1 | valid, valid | art-250, art-252-inc-II |
| q-084 | deadline_or_value | False |  | 1 | valid | art-276 |
| q-020 | deadline_or_value | False |  | 1 | valid | art-651 |
| q-048 | deadline_or_value | False |  | 1 | valid | art-365-p2 |
| q-060 | unanswerable | True | insufficient_context | 0 |  |  |
| q-058 | unanswerable | False |  | 1 | valid, valid | art-250-p2, art-250-inc-I |
| q-029 | unanswerable | True | insufficient_context | 0 |  |  |
