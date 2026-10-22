"""Sanity report: every output count next to the raw count in the HTML, differences explained."""

import random
import re
from collections import Counter

from bs4 import Tag

from aneel_rag.ingest.html_load import FORBIDDEN
from aneel_rag.ingest.labels import parse_label
from aneel_rag.ingest.models import Manifest
from aneel_rag.ingest.parser import ParseResult
from aneel_rag.ingest.segment import Line

SAMPLE_SEED = 1000
SAMPLE_SIZE = 10
CHANGE = re.compile(r"\(\s*Redação\s+(dada|acrescida)", re.IGNORECASE)
REVOKED = re.compile(r"\(\s*Revogad", re.IGNORECASE)


def _top_level(root: Tag, name: str) -> list[Tag]:
    return [t for t in root.find_all(name) if t.find_parent(name) is None]


def _annotation_positions(line: Line) -> list[tuple[str, bool, bool]]:
    """(kind, struck, bold) for each "(Redação dada|acrescida" in the line, from its first char."""
    chars, flags = [], []
    for run in line.runs:
        chars.append(run.text)
        flags.extend([(run.struck is not None, run.bold)] * len(run.text))
    raw = "".join(chars)
    return [(m.group(1).lower(), *flags[m.start()]) for m in CHANGE.finditer(raw)]


def annotation_tally(result: ParseResult) -> Counter:
    tally: Counter = Counter()
    for i, c in enumerate(result.items):
        section = result.section_at[i]
        for kind, struck, bold in _annotation_positions(c.line):
            if c.is_heading:
                key = "headings"
            elif section == "annex":
                key = "annexes"
            elif section != "norm":
                key = f"other: {section}"
            elif struck:
                key = (
                    "other: revoked wording"
                    if c.state == "revoked"
                    else "other: superseded wording"
                )
            elif c.state != "keep":
                key = "other: old annotation right after struck wording"
            elif bold:
                key = "amended (in <b>)" if kind == "dada" else "added (in <b>)"
            else:
                key = f"outside <b> ({kind})"
            tally[key] += 1
    return tally


def struck_tally(result: ParseResult) -> Counter:
    category: dict[int, str] = {}
    for i, c in enumerate(result.items):
        for sid in c.line.struck_ids:
            if c.state == "revoked":
                cat = "revoked (kept, not indexed)"
            elif c.is_heading:
                cat = "superseded heading"
            elif result.section_at[i] == "annex":
                cat = "annex, superseded"
            elif c.line.kind == "row":
                cat = "table cell, superseded"
            else:
                cat = "superseded wording (dropped)"
            category.setdefault(sid, cat)
    return Counter(category.values())


def _row(*cells) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |"


def render(result: ParseResult, root: Tag, manifest: Manifest) -> str:
    units = result.units
    status = Counter(u.status for u in units if u.doc_type == "norm")
    out = [
        "# Ingest report",
        "",
        f"- Corpus: `{manifest.corpus_path}` (sha256 `{manifest.corpus_sha256}`)",
        f"- Parser version: {manifest.parser_version}; run on {manifest.generated_on}",
        f"- Units: {len(units)} ({sum(u.doc_type == 'norm' for u in units)} norm, "
        f"{sum(u.doc_type == 'annex' for u in units)} annex)",
        "",
    ]

    # ---- articles -----------------------------------------------------------------------
    spans = root.select("span.artigo")
    struck_spans = [s for s in spans if s.find_parent("s")]
    revoked_articles = [u for u in units if u.kind == "caput" and u.status == "revoked"]
    live_articles = [u for u in units if u.kind == "caput" and u.status != "revoked"]
    fallback = len(result.fallback_articles)
    superseded_spans = len(struck_spans) - len(revoked_articles)
    out += [
        "## 1. Counts against the raw HTML",
        "",
        "### Articles",
        "",
        _row("Parser output", "Count", "Raw HTML", "Count"),
        _row("---", "---:", "---", "---:"),
        _row("live articles", len(live_articles), "`span.artigo`", len(spans)),
        _row("revoked articles", len(revoked_articles), "inside `<s>`", len(struck_spans)),
        _row("articles without a span (fallback)", fallback, "", ""),
        _row("superseded old versions (dropped)", superseded_spans, "", ""),
        "",
        f"Check: {len(live_articles)} live - {fallback} without span + {len(revoked_articles)} "
        f"revoked + {superseded_spans} superseded = "
        f"{len(live_articles) - fallback + len(revoked_articles) + superseded_spans} "
        f"(raw {len(spans)}). Without span: {', '.join(result.fallback_articles) or 'none'}.",
        "",
    ]

    # ---- struck text --------------------------------------------------------------------
    s_raw = len(_top_level(root, "s"))
    s_tally = struck_tally(result)
    out += ["### Struck text (`<s>`)", "", _row("Category", "Count"), _row("---", "---:")]
    out += [_row(k, v) for k, v in sorted(s_tally.items())]
    out += [_row("**total**", sum(s_tally.values())), "", f"Raw top-level `<s>`: {s_raw}.", ""]
    if sum(s_tally.values()) != s_raw:
        out += [f"**Residual: {s_raw - sum(s_tally.values())}** `<s>` without text lines.", ""]

    # ---- annotations --------------------------------------------------------------------
    text = root.get_text()
    raw_change = Counter(m.group(1).lower() for m in CHANGE.finditer(text))
    tally = annotation_tally(result)
    bs = _top_level(root, "b")
    b_with = sum(bool(CHANGE.search(b.get_text())) for b in bs)
    in_b = sum(len(CHANGE.findall(b.get_text())) for b in bs)
    in_s = sum(len(CHANGE.findall(s.get_text())) for s in _top_level(root, "s"))
    total = sum(raw_change.values())
    out += [
        "### Amendment annotations (“Redação dada” / “Redação acrescida”)",
        "",
        f"Raw occurrences in the HTML text: **{total}** "
        f"({raw_change['dada']} “Redação dada” + {raw_change['acrescida']} “Redação acrescida”). "
        "Each occurrence is counted once below, where it sits:",
        "",
        _row("Where", "Count"),
        _row("---", "---:"),
    ]
    out += [_row(k, v) for k, v in sorted(tally.items())]
    residual = total - sum(tally.values())
    out += [_row("**total**", sum(tally.values())), _row("residual", residual), ""]
    out += [
        f"Why 339 → {total}: the planning inspection counted **`<b>` elements** containing "
        f"at least "
        f"one annotation of either kind ({b_with}), not occurrences of “Redação dada”. "
        f"Those `<b>` hold {in_b} occurrences (some hold two), {in_s} sit inside `<s>` (old "
        f"wording) and {total - in_b - in_s} are plain text outside both "
        "(the `outside <b>` rows above, net of any inside `<s>`).",
        "",
    ]
    out += [
        "Unit status (norm): "
        + ", ".join(f"{k}: {status[k]}" for k in ("active", "amended", "added", "revoked")),
        "— an unannotated bold line inherits the next annotation of its bold block, and a unit "
        "whose head is unannotated but whose continuation lines are annotated is `amended`, so "
        "unit counts differ from annotation counts by design.",
        "",
    ]

    # ---- revoked ------------------------------------------------------------------------
    revoked_lines = [
        i
        for i, c in enumerate(result.items)
        if c.state == "revoked" and REVOKED.search(c.line.text(keep_struck=False))
    ]
    line_to_unit = {i: uid for uid, idx in result.unit_lines.items() for i in idx[:1]}
    out += [
        "### Revocations",
        "",
        f"Raw “(Revogado pela …)”: {len(REVOKED.findall(text))}. "
        f"Revoked units: {sum(u.status == 'revoked' for u in units)}. Expansion per annotation:",
        "",
        _row("Annotation line", "Revoked units", "Units"),
        _row("---", "---:", "---"),
    ]
    for i in revoked_lines:
        j = i
        # A block ends where the previous revocation annotation closed its own block.
        while j - 1 >= 0 and result.items[j - 1].state == "revoked" and j - 1 not in revoked_lines:
            j -= 1
        ids = [line_to_unit[k] for k in range(j, i + 1) if k in line_to_unit]
        shown = ", ".join(f"`{x}`" for x in ids[:6]) + (" …" if len(ids) > 6 else "")
        out.append(_row(i, len(ids), shown))
    out.append("")

    # ---- article sequence ---------------------------------------------------------------
    numbers = Counter()
    for u in units:
        if u.kind == "caput" and (lbl := parse_label(u.label)):
            numbers[lbl.key] += 1
    plain = sorted({n for n, s in numbers if not s})
    gaps = [n for n in range(1, max(plain) + 1) if n not in plain]
    dups = [k for k, v in numbers.items() if v > 1]
    revoked_nums = {parse_label(u.label).number for u in revoked_articles}
    out += [
        "## 2. Article sequence 1-" + str(max(plain)),
        "",
        f"- Articles with a letter suffix: {sum(1 for n, s in numbers if s)}",
        "- Gaps: "
        + (
            ", ".join(f"{n} ({'revoked' if n in revoked_nums else 'unexplained'})" for n in gaps)
            or "none"
        ),
        "- Duplicates: " + (", ".join(map(str, dups)) or "none"),
        "",
    ]

    # ---- diagnostics --------------------------------------------------------------------
    out += ["## 3. Rejected labels (kept as continuation text)", ""]
    out += [_row("Article", "Label", "Reason", "Text"), _row("---", "---", "---", "---")]
    out += [_row(r["article"], r["label"], r["reason"], r["text"]) for r in result.rejected]
    out += ["", "## 4. Defects of the official text, handled", ""]
    out += [_row("Kind", "Article", "After", "Label"), _row("---", "---", "---", "---")]
    out += [_row(g["kind"], g["article"], g["after"], g["label"]) for g in result.gaps]
    out += ["", "## 5. Inline label repairs (a gap whose labels sit inside the previous unit)", ""]
    if result.inline_repairs:
        out += [_row("Article", "Split from", "New unit", "Text"), _row("---", "---", "---", "---")]
        out += [
            _row(r["article"], f"`{r['from']}`", f"`{r['unit']}`", r["text"])
            for r in result.inline_repairs
        ]
    else:
        out.append("None.")
    top = result.continuation.most_common(10)
    out += ["", "## 6. Continuation lines per article (top 10)", ""]
    out += [_row("Article", "Lines"), _row("---", "---:")] + [_row(a, n) for a, n in top]
    out += [
        "",
        f"Total continuation lines: {sum(result.continuation.values())}.",
        "",
        "## 7. Quotations of other norms",
        "",
        "Units flagged `quotes_other_norm` (still indexed): "
        + ", ".join(sorted({u.article_id for u in units if u.quotes_other_norm})),
        "",
        "Quotations closed by the end of the article instead of “(NR)”: "
        + (", ".join(result.quotes_without_nr) or "none"),
        "",
        "## 8. Orphan struck blocks (no new version and no “Revogado”)",
        "",
    ]
    if result.orphans:
        out += [_row("Lines", "Article", "Text"), _row("---", "---", "---")]
        out += [_row(o["lines"], o["article"], o["text"]) for o in result.orphans]
    else:
        out.append("None.")
    out += ["", "## 9. Superseded headings", ""]
    out += [f"- {h}" for h in result.superseded_headings] or ["None."]
    out += ["", "## 10. Revoked units", ""]
    out += [f"- `{u.id}` — {u.text[:100]}" for u in units if u.status == "revoked"]
    out += ["", "## 11. Validity notes", ""]
    out += [f"- `{u.id}`: {n}" for u in units for n in u.notes]
    out += [f"- preamble: {n}" for n in result.preamble.get("notes", [])]
    owner = {i: uid for uid, idx in result.unit_lines.items() for i in idx}
    dropped_notes = [
        (i, a.text)
        for i, c in enumerate(result.items)
        if c.state == "superseded"
        for a in c.found
        if a.kind == "note"
    ]
    if dropped_notes:
        out += ["", "Notes inside superseded (struck) wording, dropped with it:", ""]
        for i, note in dropped_notes:
            nxt = next((owner[k] for k in range(i + 1, len(result.items)) if k in owner), None)
            out.append(f"- line {i}, before `{nxt}`: {note}")
    out += ["", "## 12. Dropped text", ""]
    out += [f"- {d}" for d in result.dropped] or ["None."]

    # ---- sample -------------------------------------------------------------------------
    live = sorted(
        (u for u in units if u.doc_type == "norm" and u.status != "revoked"), key=lambda u: u.id
    )
    sample = random.Random(SAMPLE_SEED).sample(live, SAMPLE_SIZE)
    out += [
        "",
        f"## 13. Sample of {SAMPLE_SIZE} units (seed {SAMPLE_SEED}) to check in the browser",
        "",
        _row("Unit", "Anchor", "Status", "Text", "Link"),
        _row("---", "---", "---", "---", "---"),
    ]
    for u in sample:
        link = f"[open]({u.source_url})" if u.source_url else "—"
        out.append(_row(f"`{u.id}`", f"`{u.source_anchor}`", u.status, u.text[:80], link))

    problems = blocking_problems(result)
    out += ["", "## 14. Checks", ""]
    out += [f"- FAIL: {p}" for p in problems] or ["- All blocking checks passed."]
    out.append(f"- Units without `source_url`: {sum(u.source_url is None for u in units)}")
    return "\n".join(out) + "\n"


def blocking_problems(result: ParseResult) -> list[str]:
    problems = []
    live_ids = Counter(u.id for u in result.units if u.status != "revoked")
    if dups := [k for k, v in live_ids.items() if v > 1]:
        problems.append(f"duplicate ids among live units: {dups[:10]}")
    if result.duplicate_ids:
        problems.append(f"duplicate ids: {result.duplicate_ids[:10]}")
    for unit in result.units:
        if leaked := [s for s in FORBIDDEN if s in unit.text]:
            problems.append(f"{unit.id} contains {leaked}")
    if live_drop := [d for d in result.dropped if d["reason"] == "text outside any unit"]:
        problems.append(f"{len(live_drop)} live text lines dropped")
    return problems
