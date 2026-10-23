# aneel-regulatory-rag

Question answering over **ANEEL Normative Resolution No. 1,000/2021** (compiled text, Brazilian Portuguese)
where every answer cites the article/paragraph/item it comes from, and the system abstains when the
norm does not answer the question.

> **Personal project.** Built for learning and as a portfolio piece. It has no relation to any
> employer or client and uses only the public text of the norm.

**Status:** work in progress — phase 2 (chunking, indexing and retrieval). Results: TBD.

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
make qdrant-up
make index      # chunks data/processed/units.jsonl, embeds with bge-m3 and loads Qdrant
uv run python -m aneel_rag.retrieval.query "prazo para religação" --mode hybrid+rerank
```

Chunks are structural: one per article, with long articles split along the device tree and every
piece repeating the heading path and the caput ([ADR-002](docs/adr/002-html-structural-parsing-and-deep-links.md)).
Retrieval has four modes: `dense`, `sparse`, `hybrid` (Qdrant RRF over the bge-m3 dense and
lexical vectors) and `hybrid+rerank` (bge-reranker-v2-m3 over the top 20). Revoked devices and
annexes are excluded by default; `--include-revoked` and `--include-annexes` lift the filters
([ADR-003](docs/adr/003-hybrid-retrieval.md)). The first run downloads the models (about 4.5 GB),
and document embeddings are cached in `data/cache/`.

## Layout

| Path | Purpose |
|---|---|
| `src/aneel_rag/` | Package: ingest, chunking, retrieval, graph, llm, observability, api |
| `config/` | All result-affecting parameters (`.env` holds only secrets/endpoints) |
| `data/raw/SOURCE.md` | Corpus provenance and SHA-256 hashes |
| `eval/` | Dataset, metrics and dated reports |
| `docs/adr/` | Architecture decision records |

## Sobre (PT-BR)

Projeto pessoal de perguntas e respostas sobre a REN ANEEL nº 1.000/2021, com citação obrigatória
do dispositivo de origem e abstenção quando a norma não responde. Sem relação com empregador ou
cliente.
