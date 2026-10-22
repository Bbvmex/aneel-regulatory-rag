"""State machine that turns classified lines into citable units.

Articles come from span.artigo; §, incisos and alíneas from labels at the start of a line,
accepted only when they continue the current sequence (struck labels included), so formula
variables such as "C - é o consumo" stay continuation text.
"""

import re
from collections import Counter
from dataclasses import dataclass, field, replace

from aneel_rag.ingest import annotations as ann
from aneel_rag.ingest.labels import (
    DASHES,
    Label,
    int_to_roman,
    is_successor,
    parse_article_id,
    parse_label,
)
from aneel_rag.ingest.models import Amendment, Unit
from aneel_rag.ingest.segment import Line
from aneel_rag.ingest.vigencia import Classified, classify, orphan_struck_blocks

HEADING_LEVELS = {"TÍTULO": 0, "CAPÍTULO": 1, "SEÇÃO": 2, "SUBSEÇÃO": 3}
QUOTE_OPEN = ('"', "“")
SIGNATURE = re.compile(r"^[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ .'-]+$")
FOOTER_MARK = "Este texto não substitui"
# A § label glued after other text, opening a capitalized sentence.
MID_PAR = re.compile(r"(?<=\S)\s+(§\s*(\d+)\s*º?)\s+(?=[A-ZÀ-Ý])")


@dataclass
class _Draft:
    id: str
    kind: str
    label: str
    parent_id: str | None
    article_id: str | None
    path: list[str]
    anchor: str
    doc_type: str
    items: list[Classified] = field(default_factory=list)
    quotes: bool = False


@dataclass
class ParseResult:
    units: list[Unit]
    items: list[Classified]
    preamble: dict
    footer: list[str]
    rejected: list[dict] = field(default_factory=list)
    continuation: Counter = field(default_factory=Counter)
    quotes_without_nr: list[str] = field(default_factory=list)
    fallback_articles: list[str] = field(default_factory=list)
    orphans: list[dict] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)
    superseded_headings: list[str] = field(default_factory=list)
    duplicate_ids: list[str] = field(default_factory=list)
    gaps: list[dict] = field(default_factory=list)
    inline_repairs: list[dict] = field(default_factory=list)
    section_at: list[str] = field(default_factory=list)  # preamble | norm | footer | annex
    unit_lines: dict[str, list[int]] = field(default_factory=dict)


class _Parser:
    def __init__(self, items: list[Classified]) -> None:
        self.items = items
        self.units: list[Unit] = []
        self.drafts_by_id: dict[str, _Draft] = {}
        self.section = "preamble"
        self.headings: dict[int, str] = {}
        self.preamble: dict = {"lines": []}
        self.footer: list[str] = []
        self.result_extra: dict = {
            "rejected": [],
            "continuation": Counter(),
            "quotes_without_nr": [],
            "fallback_articles": [],
            "dropped": [],
            "superseded_headings": [],
            "gaps": [],
            "inline_repairs": [],
        }
        # article context
        self.article: _Draft | None = None
        self.article_label: Label | None = None
        self.last_live_article: Label | None = None
        self.art_quotes: set[str] = set()
        self.ordinal = 0
        self.par: _Draft | None = None
        self.inc: _Draft | None = None
        self.seen: dict[str, Label | None] = {"par": None, "inc": None, "al": None}
        self.seen_struck = {"par": False, "inc": False, "al": False}
        self.current: _Draft | None = None
        self.quote_open = False
        # annex context
        self.annex: str | None = None
        self.annex_title = ""
        self.annex_header: list[str] | None = None
        self.annex_rows = 0
        self.annex_clauses = 0

    # ---- helpers -------------------------------------------------------------------------
    def _path(self, *devices: str) -> list[str]:
        return [self.headings[k] for k in sorted(self.headings)] + list(devices)

    def _finish(self) -> None:
        self.current = None

    def _new(self, draft: _Draft, head: Classified) -> _Draft:
        existing = self.drafts_by_id.get(draft.id)
        if head.state == "keep" and existing and existing.items[0].state == "keep":
            n = 2
            while f"{draft.id}-{n}" in self.drafts_by_id:
                n += 1
            draft.id = f"{draft.id}-{n}"
        draft.items.append(head)
        self.drafts_by_id.setdefault(draft.id, draft)
        self._order.append(draft)
        self.current = draft
        return draft

    def _reset_devices(self) -> None:
        self.par = self.inc = None
        self.seen = {"par": None, "inc": None, "al": None}
        self.seen_struck = {"par": False, "inc": False, "al": False}

    def _close_quote(self) -> None:
        if self.quote_open and self.article:
            self.result_extra["quotes_without_nr"].append(self.article.id)
        self.quote_open = False

    # ---- main loop -----------------------------------------------------------------------
    def run(self) -> None:
        self._order: list[_Draft] = []
        self.article_at: list[str | None] = []
        self.section_at: list[str] = []
        for i, c in enumerate(self.items):
            self.article_at.append(self.article_label.display if self.article_label else None)
            self.section_at.append("annex" if c.is_heading and self._is_annex(c) else self.section)
            if self.section == "preamble" and c.line.art_span is not None:
                self.section = "norm"  # excerpts may start at an article, with no heading
            if c.is_heading:
                self.heading(c)
            elif self.section == "preamble":
                if c.state == "keep":
                    self.preamble["lines"].append((c.line.block, c.text))
            elif self.section == "footer":
                self.footer.append(c.text)
            elif self.section == "annex":
                self.annex_line(c)
            elif self._footer_starts(i, c):
                self.section = "footer"
                self._close_quote()
                self._finish()
                self.footer.append(c.text)
            else:
                self.norm_line(c)
        self._close_quote()

    @staticmethod
    def _is_annex(c: Classified) -> bool:
        return ann.strip(c.text).upper().startswith("ANEXO")

    def _footer_starts(self, i: int, c: Classified) -> bool:
        if c.state != "keep" or self.quote_open or not SIGNATURE.match(c.text):
            return False
        return any(FOOTER_MARK in n.text for n in self.items[i + 1 : i + 4])

    def heading(self, c: Classified) -> None:
        text = ann.strip(c.text)
        if c.state != "keep":
            self.result_extra["superseded_headings"].append(text)
            return
        self._close_quote()
        self._finish()
        first = text.split(" — ")[0]
        word = first.split()[0].upper() if first.split() else ""
        if word == "ANEXO":
            self.section = "annex"
            self.annex = first.split()[1] if len(first.split()) > 1 else str(len(self.units))
            self.annex_title = text
            self.annex_header = None
            self.annex_rows = self.annex_clauses = 0
            self.headings = {0: text}
            self.article = None
            return
        if self.section == "annex":
            # Sub-headings inside an annex (form titles) are part of its text.
            self.annex_line(c)
            return
        self.section = "norm"
        level = HEADING_LEVELS.get(word)
        if level is None:
            self.result_extra["dropped"].append({"reason": "unknown heading", "text": text})
            return
        self.headings = {k: v for k, v in self.headings.items() if k < level}
        self.headings[level] = text

    # ---- norm ----------------------------------------------------------------------------
    def norm_line(self, c: Classified) -> None:
        line: Line = c.line
        if line.art_span is not None:
            label = parse_article_id(line.art_span) or parse_label(c.text)
            if label is not None:
                self.start_article(c, label, line.art_span)
                return
        if self.quote_open:
            self.append(c)
            if "(NR)" in c.text:
                self.quote_open = False
            return
        if c.state != "superseded" and c.text.lstrip().startswith(QUOTE_OPEN) and self.current:
            self.quote_open = "(NR)" not in c.text
            self.art_quotes.add(self.article.id if self.article else self.current.id)
            self.append(c)
            return

        if (split := self._missing_break(c)) is not None:
            for part in split:
                self.norm_line(part)
            return

        label = parse_label(c.text) if line.kind == "text" else None
        if label is None:
            self.append(c)
            return
        if label.kind == "art":
            if c.state != "superseded" and is_successor(self.last_live_article, label):
                self.result_extra["fallback_articles"].append(label.display)
                self.start_article(c, label, None)
            else:
                self.reject(c, label, "article label without span.artigo and not a successor")
                self.append(c)
            return
        if self.article is None:
            if c.state == "superseded":
                return
            self.reject(c, label, "device label before any article")
            self.append(c)
            return
        level = "par" if label.kind in ("par", "pu") else label.kind
        prev = self.seen[level]
        same_kind = prev if prev and prev.kind == label.kind else None
        # Repeating a label is only legal right after its struck (old or revoked) version.
        repeat = same_kind is not None and same_kind.key == label.key and self.seen_struck[level]
        ok = label.kind == "pu" or repeat or is_successor(same_kind, label)
        jump = (label.number - same_kind.number) if same_kind else label.number
        if not ok and c.state == "keep" and same_kind and same_kind.key == label.key:
            # The official text repeats a few labels (Art. 668, III: two "d)"); keep both.
            self.result_extra["gaps"].append(self._gap("repeated label", prev, label))
            ok = True
        elif (
            not ok
            and not label.suffix
            and ((level == "par" and jump > 0) or (same_kind and 0 < jump <= 2))
        ):
            # Missing §§ (or one missing inciso/alínea) are gaps in the source, not false labels,
            # unless the missing labels sit inline in the previous unit (Art. 485, §§ 5º-6º).
            if same_kind and self._inline_repair(level, same_kind, label):
                prev = same_kind = self.seen[level]
                ok = is_successor(same_kind, label)
            if not ok:
                self.result_extra["gaps"].append(self._gap("gap", prev, label))
                ok = True
        if not ok:
            self.reject(c, label, f"out of sequence after {prev.display if prev else 'nothing'}")
            self.append(c)
            return
        self.seen[level] = label
        self.seen_struck[level] = c.state != "keep"
        if level == "par":
            self.seen["inc"] = self.seen["al"] = None
        elif level == "inc":
            self.seen["al"] = None
        if c.state == "superseded":
            return
        self.start_device(c, label)

    def start_article(self, c: Classified, label: Label, span_id: str | None) -> None:
        self._close_quote()
        self._reset_devices()
        self.article_label = label
        if c.state == "superseded":
            # Old wording of an article: only resets the label sequence; its new version follows.
            return
        self.last_live_article = label
        art_id = label.id_part
        anchor = span_id.strip() if span_id else f"article{label.number}."
        self.ordinal = 0
        draft = _Draft(
            id=art_id,
            kind="caput",
            label=label.display,
            parent_id=None,
            article_id=art_id,
            path=self._path(label.display),
            anchor=f"{anchor}#0",
            doc_type="norm",
        )
        self.article = self._new(draft, c)

    def start_device(self, c: Classified, label: Label) -> None:
        assert self.article is not None
        self.ordinal += 1
        art = self.article
        if label.kind in ("par", "pu"):
            parent, chain = art, [art.label, label.display]
        elif label.kind == "inc":
            parent = self.par or art
            chain = [*parent.path[len(self._path()) :], label.display]
        else:
            parent = self.inc or self.par or art
            chain = [*parent.path[len(self._path()) :], label.display]
        draft = _Draft(
            id=f"{parent.id}-{label.id_part}",
            kind=label.kind if label.kind != "pu" else "par",
            label=label.display,
            parent_id=parent.id,
            article_id=art.id,
            path=self._path(*chain),
            anchor=f"{art.anchor.split('#')[0]}#{self.ordinal}",
            doc_type="norm",
        )
        self._new(draft, c)
        if label.kind in ("par", "pu"):
            self.par, self.inc = draft, None
        elif label.kind == "inc":
            self.inc = draft

    def append(self, c: Classified) -> None:
        if c.state == "superseded":
            return
        if self.current is None:
            if ann.strip(c.text):
                self.result_extra["dropped"].append(
                    {"reason": "text outside any unit", "text": c.text}
                )
            return
        head = self.current.items[0]
        if c.state == "revoked" and head.state != "revoked":
            self.result_extra["dropped"].append(
                {
                    "reason": "revoked text after a live unit",
                    "unit": self.current.id,
                    "text": c.text,
                }
            )
            return
        if c.state == "keep" and head.state == "revoked" and ann.strip(c.text):
            self.result_extra["dropped"].append(
                {
                    "reason": "live text after a revoked unit",
                    "unit": self.current.id,
                    "text": c.text,
                }
            )
        self.current.items.append(c)
        if self.current.doc_type == "norm" and ann.strip(c.text):
            self.result_extra["continuation"][self.current.article_id] += 1

    def _missing_break(self, c: Classified) -> list[Classified] | None:
        """Split "... inciso I do § 1º § 2º Durante ..." where the source lost a <br>."""
        if c.state != "keep" or c.line.kind != "text" or self.article is None:
            return None
        prev = self.seen["par"]
        expected = prev.number + 1 if prev and prev.kind == "par" else 1
        for m in MID_PAR.finditer(c.text):
            if int(m.group(2)) == expected:
                before, after = c.text[: m.start(1)].rstrip(), c.text[m.start(1) :]
                # "§ 2º § 2º A distribuidora ..." (Art. 250) is a doubled label, not two §§.
                doubled = (lbl := parse_label(before)) is not None and lbl.raw == before
                self.result_extra["gaps"].append(
                    {"kind": "doubled label" if doubled else "missing line break",
                     "article": self.article.id, "after": prev.display if prev else None,
                     "label": m.group(1)}
                )  # fmt: skip
                if doubled:
                    return [replace(c, text=after)]
                return [
                    replace(c, text=before, found=ann.find(before, c.line.links(False))),
                    replace(c, text=after, found=ann.find(after, c.line.links(False))),
                ]
        return None

    def _inline_repair(self, level: str, prev: Label, label: Label) -> bool:
        """Recover the labels missing between prev and label from the end of the previous unit."""
        repaired = False
        for number in range(prev.number + 1, label.number):
            target = self.current
            if target is None or target.article_id != self.article.id:
                break
            if target.items[0].state != "keep":
                break
            split = _split_inline(target, _inline_label(label.kind, number))
            if split is None:
                break
            head, rest = split
            found = parse_label(head.text)
            self.seen[level], self.seen_struck[level] = found, False
            if level == "par":
                self.seen["inc"] = self.seen["al"] = None
            elif level == "inc":
                self.seen["al"] = None
            self.start_device(head, found)
            self.current.items.extend(rest)
            self.result_extra["inline_repairs"].append(
                {"article": self.article.id, "from": target.id, "unit": self.current.id,
                 "label": found.display, "text": ann.strip(head.text)[:90]}
            )  # fmt: skip
            repaired = True
        return repaired

    def _gap(self, kind: str, prev: Label | None, label: Label) -> dict:
        return {
            "kind": kind,
            "article": self.article.id if self.article else None,
            "after": prev.display if prev else None,
            "label": label.display,
        }

    def reject(self, c: Classified, label: Label, reason: str) -> None:
        self.result_extra["rejected"].append(
            {
                "article": self.article.id if self.article else None,
                "label": label.raw,
                "state": c.state,
                "reason": reason,
                "text": c.text[:120],
            }
        )

    # ---- annexes -------------------------------------------------------------------------
    def annex_line(self, c: Classified) -> None:
        if c.state == "superseded":
            return
        annex = f"annex-{self.annex}"
        text = ann.strip(c.text)
        if c.line.kind == "row":
            cells = [cell.strip() for cell in text.split(" | ")]
            if self.annex_header is None:
                self.annex_header = cells
                return
            self.annex_rows += 1
            pairs = zip(self.annex_header, cells, strict=False)
            c.text = " | ".join(f"{h}: {v}" for h, v in pairs)
            self._annex_unit(f"{annex}-row-{self.annex_rows}", f"linha {self.annex_rows}", c)
            self._finish()
            return
        if text.upper().startswith("CLÁUSULA"):
            self.annex_clauses += 1
            intro = self.drafts_by_id.get(annex)
            if intro is not None and self.annex_clauses == 1:
                intro.id = f"{annex}-intro"
            self._annex_unit(f"{annex}-cl-{self.annex_clauses}", text.split(":")[0], c)
            return
        if self.current is None or self.current.doc_type != "annex":
            self._annex_unit(annex, self.annex_title.split(" — ")[0], c)
            return
        self.append(c)

    def _annex_unit(self, uid: str, label: str, c: Classified) -> None:
        draft = _Draft(
            id=uid,
            kind="annex",
            label=label,
            parent_id=None,
            article_id=None,
            path=self._path(label),
            anchor=f"{uid}#0",
            doc_type="annex",
        )
        self._new(draft, c)


def _inline_label(kind: str, number: int) -> re.Pattern:
    """A label glued after other text that opens a capitalized sentence ("... no § 6º § 5º A")."""
    if kind == "par":
        core = rf"§\s*{number}\s*º?"
    elif kind == "inc":
        core = rf"{int_to_roman(number)}\s*[{DASHES}]"
    else:
        core = rf"{chr(96 + number)}\)"
    return re.compile(rf"(?<=\S)\s+({core})\s+(?=[A-ZÀ-Ý])")


def _split_inline(draft: _Draft, pattern: re.Pattern) -> tuple[Classified, list] | None:
    """Cut the draft at the first match; return the new head and the lines that follow it."""
    for j, c in enumerate(draft.items):
        if c.state != "keep" or not (m := pattern.search(c.text)):
            continue
        before, after = c.text[: m.start(1)].rstrip(), c.text[m.start(1) :]
        links = c.line.links(False)
        draft.items[j] = replace(c, text=before, found=ann.find(before, links))
        rest = draft.items[j + 1 :]
        del draft.items[j + 1 :]
        return replace(c, text=after, found=ann.find(after, links)), rest
    return None


def _build(draft: _Draft, quotes: bool) -> Unit:
    head = draft.items[0]
    lines, found, figures = [], [], []
    for c in draft.items:
        if text := ann.strip(c.text):
            lines.append(text)
        found.extend(c.found)
        if c.inherited and not c.own_change:
            found.append(c.inherited)
        figures.extend(c.line.figures(keep_struck=c.state == "revoked"))
    if head.state == "revoked":
        status = "revoked"
    elif head.change:
        status = head.change.kind
    elif any(c.change for c in draft.items):
        status = "amended"
    else:
        status = "active"
    return Unit(
        id=draft.id,
        parent_id=draft.parent_id,
        article_id=draft.article_id,
        kind=draft.kind,
        label=draft.label,
        hierarchy_path=draft.path,
        text="\n".join(lines),
        source_anchor=draft.anchor,
        doc_type=draft.doc_type,
        status=status,
        amended_by=[Amendment(**a) for a in ann.amendments(found)],
        notes=ann.notes(found),
        has_figure=bool(figures),
        figures=figures,
        quotes_other_norm=quotes,
    )


def _dedupe(drafts: list[_Draft]) -> list[str]:
    """Revoked units may reuse a live label; suffix them so every id stays unique."""
    clashes, seen = [], Counter()
    for d in drafts:
        seen[d.id] += 1
    for d in drafts:
        if seen[d.id] > 1 and d.items[0].state == "revoked":
            n = 1
            while f"{d.id}-rev{n if n > 1 else ''}" in seen:
                n += 1
            old, d.id = d.id, f"{d.id}-rev{n if n > 1 else ''}"
            seen[old] -= 1
            seen[d.id] += 1
    for uid, n in seen.items():
        if n > 1:
            clashes.append(uid)
    return clashes


def parse_lines(lines: list[Line]) -> ParseResult:
    items = classify(lines)
    p = _Parser(items)
    p.run()
    duplicates = _dedupe(p._order)
    units = [_build(d, (d.article_id or d.id) in p.art_quotes) for d in p._order]
    orphans = [
        {
            "lines": f"{first}-{last}",
            # The article label is updated by the struck line itself, so look one line ahead.
            "article": p.article_at[first + 1] if first + 1 < len(items) else p.article_at[first],
            "text": items[first].text[:90],
        }
        for first, last in orphan_struck_blocks(items)
    ]
    return ParseResult(
        units,
        items,
        p.preamble,
        p.footer,
        orphans=orphans,
        duplicate_ids=duplicates,
        section_at=p.section_at,
        unit_lines={d.id: [c.line.index for c in d.items] for d in p._order},
        **p.result_extra,
    )
