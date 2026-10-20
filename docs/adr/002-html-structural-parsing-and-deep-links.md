# ADR-002: Structural parsing of the official HTML, and deep links via text fragments

- **Status:** accepted (source format, deep links); chunking section to be completed in phase 2
- **Date:** 2026-10-20

## Context
The official compiled text of REN 1.000/2021 is published on leis.org (ANEEL's legislation
platform). A PDF export exists, but it renders struck-through (superseded) wording with vector
lines and places article numbers in badges outside the reading order. The HTML carries the same
information as markup: `span.artigo` per article, `span.titulo` per heading, `<s>` for superseded
or revoked wording, `<b>` for current amended/added wording.

Every answer must cite a device (article, paragraph, item), and users should be able to check the
citation against the official page.

## Decision

### Source format
Parse the HTML (`#law-content` extract, versioned as `data/raw/ren1000_law_content.html`).
The PDF is kept only for human reference.

### Deep links
The live page offers no native per-article deep link: article spans only carry
`data-summary-id` (e.g. `article23.`, normalized to `art-23`), not an `id`, and the side summary
scrolls via JavaScript without changing the URL.

Each unit therefore gets `source_url = <norm URL>#:~:text=<prefix>` (URL text fragment), where:
- `prefix` = the first `corpus.fragment_min_words` (6) words of the unit text, **without** the
  device label (`Art. N.`, `§ Nº`, `Parágrafo único.`, `IV -`, `a)`), percent-encoded, with the
  fragment-reserved characters `-`, `,`, `&` escaped;
- **uniqueness:** the normalized prefix (NFKC, case-folded, whitespace-collapsed) must occur exactly
  once in the full rendered page text, **struck-through wording included**, because the browser
  matches against everything visible. Otherwise the prefix is extended word by word. Substring
  counting is conservative (it may add a word the browser would not need, never fewer);
- revoked units get no `source_url` (their text is struck through on the page);
- if no unique prefix exists, `source_url` is `None`.

Implementation: `src/aneel_rag/ingest/source_url.py`; tests in `tests/unit/test_source_url.py`.

## Consequences
- Text fragments work in Chromium-based browsers (Chrome, Edge) **only when the page is already
  loaded** past the Cloudflare challenge. Other browsers ignore the fragment.
- **Cold links do not work** (verified manually, 2026-10-20): opening a `source_url` directly
  goes through the Cloudflare challenge, which drops the fragment; the page opens at the top.
  Fallback in every failing case = page at the top, so the link is never wrong, only less precise.
- Consequence for the UI: each citation must also show the device ID and the quoted text, so the
  user can locate it with Ctrl+F when the highlight is lost. The link is a convenience, not the
  citation itself.
- A new snapshot can change the uniqueness of prefixes; URLs are regenerated at ingestion time.

## Chunking
To be recorded in phase 2 (one chunk per article, long articles split by paragraph with caput and
hierarchy prefix; fixed-size chunking only for ablation).
