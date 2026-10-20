# ADR-002: Structural parsing of the official HTML, and deep links via text fragments

- **Status:** accepted (source format, deep links, parsing rules); chunking section to be
  completed in phase 2
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

## Markup found in the phase 1 inspection
Measured on the 2026-10-20 snapshot (`ren1000.html`, SHA in `data/raw/SOURCE.md`). Several
numbers in the original plan were corrected here.

- **Container.** The norm is `div.aneel-content`. It also holds UI chrome: download buttons
  (`[data-extra-below-epigrafe]`) and the related-norms list `div#extras`, which leaks template
  SQL (`SELECT status_consolidacao …`). The extract drops both **by selector**, not by text
  position.
- **Articles.** 745 `span.artigo`: 717 current, plus 28 inside `<s>` (25 superseded old versions,
  including two of Art. 157, and 3 whole articles revoked: 486, 667, 672). `data-summary-id`
  is `article23.` (with the dot), `article1º`, or `article371-A ` with a trailing space; the
  struck copies have no dot. **The current Art. 35 has no span** (it is plain text inside `<b>`).
- **Headings.** `span.titulo`, often nested, with `<br>` between "Seção II" and its name.
  The levels are TÍTULO, CAPÍTULO, Seção and ANEXO (no Subseção). `data-summary-id` is
  random-looking (`Seção_91C8`) and unusable. Two headings are struck and replaced; nine carry
  amendment annotations.
- **Line breaks.** A single `<br>` also separates devices (most alíneas), so `<br><br>` is not a
  device boundary. Formula explanations ("em que:", variables) are unlabelled lines.
- **Annotations.** 360 occurrences: 156 "(Redação dada …)" and 204 "(Redação acrescida …)".
  The plan's "339" counted `<b>` elements containing at least one annotation of either kind.
  12 "(Revogado pela …)". Validity notes: "(Vide …)" and "(Suspensos os efeitos …)".
  `a.link_law` carries `data-original-title=" Data da Norma: dd.mm.aaaa - ementa"`.
- **Quotations.** Arts. 672–676 rewrite other norms with quoted devices (`"Art. 4º…`, `III -`,
  `§ 1º`) up to "(NR)".
- **Noise.** `<em>ca<fig></fig>put</em>`, `<i> caput </i>`, a zero-width space, and 16 `<img>`
  formulas.
- **Defects of the official text:** "§ 2º § 2º" (Art. 250), a lost `<br>` before "§ 2º"
  (Art. 666), §§ 5º–6º missing (Art. 485), and a repeated "d)" with a missing "f)" (Art. 668, III).

## Parsing rules (phase 1)
- **Lines.** Every `<br>` ends a line. Headings and table rows are lines of their own, and inline
  tags never insert spaces. Text is stored in NFC with invisible characters removed. NFKC and
  case-folding are used only for comparisons (deep links, citation checks in phase 3), never in
  stored text.
- **Validity** (`ingest/vigencia.py`):
  - Struck text followed by "(Revogado pela …)" is `revoked`, together with the contiguous struck
    block before it, so a whole article or a § with its incisos is revoked as one unit.
  - Any other struck text is superseded and dropped, whatever label follows it. A superseded
    block with no new version and no revocation is reported as an orphan.
- **Status of current text.** It comes from the line's own annotation: "dada" gives `amended`,
  "acrescida" gives `added`. An unannotated bold line inherits the next annotation of its
  contiguous bold block. A unit whose head is unannotated but which has annotated continuation
  lines is `amended`.
- **Labels and sequences** (`ingest/labels.py`, `ingest/parser.py`):
  - Articles come from `span.artigo`. The `^Art. N` fallback applies only outside quotations, and
    only when N is the successor of the previous article.
  - §, incisos (`I -`, `I-A -`, `I - C -`, `II-A:`, `II-Programa`, en or em dash, NBSP) and
    alíneas must continue the sequence of their parent. Struck labels count too.
  - The sequence restarts at each article and §. A repeated label is legal only right after its
    struck version.
  - A label that breaks the sequence becomes continuation text and is reported (for example
    "C - é o consumo", a formula variable).
  - Missing §§, or one missing inciso or alínea, are accepted as gaps of the source. A repeated
    label becomes `…-2`. Both are reported.
- **Quotations.** A line opening with `"` inside an article starts quote mode until "(NR)", or
  until the article ends (reported). Units of those articles get `quotes_other_norm: true` and
  stay indexed.
- **Notes and amending acts.** "(Vide …)" and "(Suspensos …)" go to `notes` and are removed from
  the text. `amended_by` lists `{kind, norma, data}` of the **current** wording only.
- **Outside the units.**
  - The preamble (title, ementa, enacting clause, notes) and the footer (signature, DOU notes)
    go to `manifest.json`.
  - Annex I is split by clause (`annex-I-intro`, `annex-I-cl-N`). Annexes II and III are one
    unit each. Annex IV gets one unit per table row, with the header repeated
    (`annex-IV-row-N`).
  - A table inside an article (Art. 519) is continuation text, one row per line.
- **IDs:** `art-23`, `art-48-a`, `art-23-p1`, `art-23-pu`, `art-2-inc-I-A`,
  `art-23-p1-inc-II-al-a`. A revoked unit that reuses a live label gets `-rev`. `source_anchor`
  is `<data-summary-id>#<ordinal of the device in the article>`.

Every count above is checked against the raw HTML in `data/processed/ingest_report.md`
(reconciliation tables) and by `tests/unit/test_ingest_corpus.py`.

## Chunking
To be recorded in phase 2 (one chunk per article, long articles split by paragraph with caput and
hierarchy prefix; fixed-size chunking only for ablation).
