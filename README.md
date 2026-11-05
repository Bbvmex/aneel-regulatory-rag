# aneel-regulatory-rag

Question answering over **ANEEL Normative Resolution No. 1,000/2021** (compiled text, Brazilian Portuguese)
where every answer cites the article/paragraph/item it comes from, and the system abstains when the
norm does not answer the question.

> **Personal project.** Built for learning and as a portfolio piece. It has no relation to any
> employer or client and uses only the public text of the norm.

**Status:** work in progress — phase 3 (answer graph, citation validation and abstention). Results: TBD.

Each citation shows the device ID and the quoted text, plus a link to the official ANEEL page
(leis.org) using a URL text fragment. The passage is highlighted only in Chromium-based browsers
when opened inside a browser that already has the page loaded; a link opened cold goes through the
site's bot challenge and lands at the top of the page. In that case, press Enter in the address
bar to apply the fragment again (the citation UI of phase 7 repeats this note). See [ADR-002](docs/adr/002-html-structural-parsing-and-deep-links.md).

## Quick start

Requires [uv](https://docs.astral.sh/uv/), GNU make and Docker.

```bash
cp .env.example .env      # fill in API keys
make setup                # .venv with Python 3.12 + dev tools + pre-commit hooks
make test
make qdrant-up
```

Run `make help` for every task.

## Ingestion

```bash
make ingest     # data/raw/ren1000_law_content.html -> data/processed/
```

The parser reads only the versioned extract of the norm and writes `units.jsonl` (one citable
device per line: caput, §, inciso, alínea or annex piece, with status `active | amended | added |
revoked`, amending acts and validity notes), `manifest.json` (corpus SHA-256, preamble, footer) and
`ingest_report.md`, which reconciles every output count with the raw HTML and lists the defects of
the official text it had to handle. Superseded (struck-through) wording is dropped; revoked
devices are kept but excluded from retrieval by default.

`make extract` regenerates the extract from a manual snapshot of the leis.org page
(`data/raw/ren1000.html`, not versioned), and `make fixtures` re-cuts the test fixtures from it.

## Indexing and retrieval

```bash
make setup-ml   # CPU torch + FlagEmbedding (local only, not used in CI)
make models     # one-time download of the pinned model revisions (the only networked step)
make qdrant-up
make index      # chunks data/processed/units.jsonl, embeds with bge-m3 and loads Qdrant
make query Q="prazo para religação" MODE=hybrid+rerank
```

Chunks are structural: one per article, with long articles split along the device tree and every
piece repeating the heading path and the caput ([ADR-002](docs/adr/002-html-structural-parsing-and-deep-links.md)).
Retrieval has four modes: `dense`, `sparse`, `hybrid` (Qdrant RRF over the bge-m3 dense and
lexical vectors) and `hybrid+rerank` (bge-reranker-v2-m3 over the top 20). Revoked devices and
annexes are excluded by default; `--include-revoked` and `--include-annexes` lift the filters
([ADR-003](docs/adr/003-hybrid-retrieval.md)). Models are pinned to Hub commits
in `config/default.yaml` and loaded offline from the local cache after `make models`. Document
embeddings are cached in `data/cache/`, and every index is stamped with the corpus, parser and
index config it was built from, so a stale index is refused.

## Answering

```bash
make ask Q="Qual o prazo de religação após a suspensão por falta de pagamento?"
```

A LangGraph pipeline retrieves and reranks, asks the generator (`gemini-3.8-flash`) whether the
excerpts answer the question, and only then generates an answer with citations
`{unit_id, quote}`. Every citation is checked deterministically: the unit must be among those
retrieved, and the quote (20 to 300 characters) must be a verbatim passage of that unit's text
after normalizing case, spacing, quotes and dashes. Citing an article for a passage of one of its
paragraphs is accepted but flagged `imprecise`. A failed check gets one retry with the errors;
after that, or when the excerpts are not enough, the system abstains and shows the three closest
excerpts ([ADR-004](docs/adr/004-citation-validation-and-abstention.md)). The model endpoint is a
config switch between Gemini and a local llama.cpp server
([ADR-006](docs/adr/006-llm-provider.md)). `make ask` needs `LLM_API_KEY` in `.env`, the index
from the previous section, and the cached models.

## Layout

| Path | Purpose |
|---|---|
| `src/aneel_rag/` | Package: ingest, chunking, retrieval, graph, llm, observability, api |
| `config/` | All result-affecting parameters (`.env` holds only secrets/endpoints) |
| `prompts/` | Versioned prompt templates (part of the config hash) |
| `data/raw/SOURCE.md` | Corpus provenance and SHA-256 hashes |
| `eval/` | Dataset, metrics and dated reports |
| `docs/adr/` | Architecture decision records |

## Sobre (PT-BR)

Projeto pessoal de perguntas e respostas sobre a REN ANEEL nº 1.000/2021, com citação obrigatória
do dispositivo de origem e abstenção quando a norma não responde. Sem relação com empregador ou
cliente.
