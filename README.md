# aneel-regulatory-rag

Question answering over **ANEEL Normative Resolution No. 1,000/2021** (compiled text, Brazilian Portuguese)
where every answer cites the article/paragraph/item it comes from, and the system abstains when the
norm does not answer the question.

> **Personal project.** Built for learning and as a portfolio piece. It has no relation to any
> employer or client and uses only the public text of the norm.

**Status:** work in progress — phase 0 (scaffold). Results: TBD.

Each citation shows the device ID and the quoted text, plus a link to the official ANEEL page
(leis.org) using a URL text fragment. The passage is highlighted only in Chromium-based browsers
with the page already open; a link opened cold goes through the site's bot challenge and lands at
the top of the page. See [ADR-002](docs/adr/002-html-structural-parsing-and-deep-links.md).

## Quick start

Requires [uv](https://docs.astral.sh/uv/), GNU make and Docker.

```bash
cp .env.example .env      # fill in API keys
make setup                # .venv with Python 3.12 + dev tools + pre-commit hooks
make test
make qdrant-up
```

Run `make help` for every task.

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
