# ADR-008: Local generator, Qwen3.6-35B-A3B on llama.cpp

- **Status:** accepted
- **Date:** 2026-11-12

## Context
The Gemini free tier cannot carry an evaluation run (decision 45), so the phase 5 generator is a
local model behind the same OpenAI-compatible interface (ADR-006). The hardware is a laptop with
an RTX 2070 Super (8 GB VRAM), 64 GB of RAM and an i7-10870H, and it overheats under long GPU
load. The generator must read Brazilian legal text, return JSON that matches a schema, copy
verbatim quotes and abstain when the excerpts do not answer. It also runs `grade_context`.

## Candidates
Searched on 2026-11-12 in the Qwen and Gemma families, keeping what fits 8 GB of VRAM plus RAM
offload:

| Model | Released | Shape | GGUF used |
|---|---|---|---|
| Qwen3.6-35B-A3B | 2026-04 | MoE, 3B active | `unsloth/Qwen3.6-35B-A3B-GGUF`, UD-Q4_K_M |
| Qwen3.5-9B | 2026-03 | dense | `unsloth/Qwen3.5-9B-GGUF`, Q5_K_M |
| Gemma 4 26B-A4B | 2026-04 | MoE, 4B active | `google/gemma-4-26B-A4B-it-qat-q4_0-gguf` (QAT) |
| Gemma 4 12B | 2026-06 | dense | `google/gemma-4-12B-it-qat-q4_0-gguf` (QAT) |

Left out: Qwen3.8-Flash-Next (125B total plus 51B of n-gram embeddings, beyond 64 GB of RAM) and
the dense 27B to 31B models (Qwen3.6-27B, Qwen3.8-27B, Gemma 4 31B), too slow with most layers
on the CPU.

## Pilot
`make generator-pilot` (`eval/generator_pilot.py`, `config/pilots/generator.yaml`) runs each
candidate through the real graph against `llama-server`: 3 validated questions per category
(seed 20261112), thinking off, `--fit` sizing the GPU offload, pauses between questions and a
wait whenever the GPU passes 80 °C. It is a pilot to choose a model, not an evaluation.

Report: [`eval/reports/2026-11-12_c2b8452_487b79b3beea_generator-pilot.md`](../../eval/reports/2026-11-12_c2b8452_487b79b3beea_generator-pilot.md).

- Qwen3.6-35B-A3B: 9/9 answerable questions answered citing the expected unit, all citations
  valid, 3/3 unanswerable abstained, one citation retry that succeeded.
- Gemma 4 26B-A4B: 9/9 and 3/3, no retries.
- Qwen3.5-9B: 3/3 abstentions, but on q-048 it cited `art-369` instead of `art-365-p2` (8/9).
- Gemma 4 12B: 9/9, but it answered the unanswerable q-058 instead of abstaining (2/3), and its
  generation was about a third as fast as the others.
- Generation speed: 29.3 tokens/s for Qwen3.6-35B-A3B, 22.8 for Gemma 4 26B-A4B (median).

**Bracket finding.** An exploratory run before this report, with the earlier prompt, showed
Qwen3.5-9B and Gemma 4 12B writing `unit_id` with the brackets of the context lines
(`[art-207-inc-IV-al-b]`), so every citation failed validation and the graph abstained on correct
answers. `prompts/generate.md` said "copied exactly from the brackets". The prompt and the
`Citation.unit_id` schema description now say to write the ID without the brackets, with an
example; no candidate wrote brackets in the report run. The same exploratory run had Gemma 4
26B-A4B fail one verbatim quote, while Qwen3.6-35B-A3B passed every question in both runs.

## Decision
- **Generator: Qwen3.6-35B-A3B**, `unsloth/Qwen3.6-35B-A3B-GGUF`, file
  `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`, SHA-256 `ac0e2c11…e31a61`, on llama.cpp build `b12110`
  (release v0.9.0, Windows CUDA 12.4). It was the only candidate without a miss in both runs, and
  its MoE shape keeps most weights in RAM, which suits the 8 GB card. Gemma 4 26B-A4B is the
  fallback.
- **Pinning.** The `local_llm` config section holds the GGUF repo, file, SHA-256 and
  quantization, the llama.cpp build and the server settings (`ctx_size` 16384, 8 threads, flash
  attention, `fit_target_mib` 1024, reasoning off). Validation rejects a SHA-256 that is not 64
  hex characters and a build that is not a `bNNNNN` tag. `models.generator` is the alias the
  server reports in `/v1/models`, which `make smoke` checks.
- **Serving.** `make llm-server` (`aneel_rag.llm.server`) hashes the GGUF (cached by path, size
  and modification time), checks `llama-server --version` against the pinned build, and refuses
  to start on any mismatch. The machine paths `GGUF_DIR` and `LLAMA_SERVER_BIN` live in `.env`;
  everything that changes results stays in config.
- **Thinking off.** Reasoning traces would make replies longer and less predictable, and the
  graph already validates and retries.

## Alternatives considered
- **Qwen3.5-9B.** It fits fully in VRAM and has the fastest prompt processing, but it cited the
  wrong unit once and keeps the GPU at full load, which this laptop does not tolerate for long.
- **Gemma 4 26B-A4B.** Equal in the report run, with lower generation speed and a quote failure
  in the exploratory run. Kept as the fallback.
- **Keep Gemini.** The free quota cannot run 90 questions with retries, and an API generator
  makes runs depend on quota and endpoint availability.

## Consequences
- Generation needs a running `make llm-server`; the GPU reached 84 °C in the pilot, so long runs
  keep the pauses and the temperature wait.
- The seconds per question in the pilot report are not comparable across candidates: the reranker
  cache filled during the first candidate. The token rates are comparable.
- Changing the generator means a new pilot report and a new pin, decided with the user.
- The judge stays `gemini-3.1-pro-preview` (ADR-006); RAGAS metrics remain TBD until there is
  quota (ADR-005).
