"""Validity of each line: current, superseded (dropped) or revoked (kept, not indexed by default).

Rules (ADR-002):
- struck text closed by "(Revogado pela ...)" is revoked, together with the contiguous struck
  block right before it (a whole article or a § with its incisos);
- any other struck text is superseded wording and is dropped, whatever label follows it;
- the status of current text comes from its own annotation; an unannotated bold line inherits
  the next annotation in the same contiguous bold block.
"""

import re
from dataclasses import dataclass, field

from aneel_rag.ingest import annotations as ann
from aneel_rag.ingest.labels import parse_label
from aneel_rag.ingest.segment import Line, collapse

_ANNOT_TAIL = re.compile(r"\(\s*(?:Redação|Revogad|Vide|Suspens).*$", re.IGNORECASE)


@dataclass
class Classified:
    line: Line
    state: str  # keep | superseded | revoked
    text: str  # text with annotations, from the runs that survive
    found: list[ann.Annotation] = field(default_factory=list)
    inherited: ann.Annotation | None = None
    bold: bool = False

    @property
    def own_change(self) -> ann.Annotation | None:
        return next((a for a in self.found if a.kind in ("amended", "added")), None)

    @property
    def change(self) -> ann.Annotation | None:
        return self.own_change or self.inherited

    @property
    def is_heading(self) -> bool:
        return self.line.kind == "heading"


def _is_bold(line: Line) -> bool:
    text = collapse("".join(r.text for r in line.runs if r.bold and r.struck is None))
    text = _ANNOT_TAIL.sub("", ann.ANNOTATION.sub(" ", text))
    return bool(re.search(r"\w", text))


def _revoked_lines(lines: list[Line]) -> set[int]:
    revoked: set[int] = set()
    for i, line in enumerate(lines):
        live = line.text(keep_struck=False)
        if not any(a.kind == "revoked" for a in ann.find(live)):
            continue
        if line.any_struck:
            revoked.add(i)
        j = i - 1
        while j >= 0 and lines[j].all_struck and lines[j].kind != "heading":
            revoked.add(j)
            j -= 1
    return revoked


def classify(lines: list[Line]) -> list[Classified]:
    revoked = _revoked_lines(lines)
    out: list[Classified] = []
    for i, line in enumerate(lines):
        if i in revoked:
            text = line.text()
            out.append(Classified(line, "revoked", text, ann.find(text, line.links())))
            continue
        if line.all_struck:
            text = line.text()
            out.append(Classified(line, "superseded", text, ann.find(text, line.links())))
            continue
        text = line.text(keep_struck=False)
        found = ann.find(text, line.links(keep_struck=False))
        if line.any_struck and not ann.strip(text):
            # Struck wording whose only live remainder is its own old annotation.
            out.append(Classified(line, "superseded", line.text(), ann.find(line.text())))
            continue
        out.append(Classified(line, "keep", text, found, bold=_is_bold(line)))

    for i, c in enumerate(out):
        if c.state != "keep" or not c.bold or c.own_change or c.is_heading:
            continue
        for nxt in out[i + 1 :]:
            if nxt.state != "keep" or not nxt.bold or nxt.is_heading:
                break
            if nxt.own_change:
                c.inherited = nxt.own_change
                break
    return out


def orphan_struck_blocks(items: list[Classified]) -> list[tuple[int, int]]:
    """Superseded blocks with no new version after them: (first, last) indexes."""
    orphans, i = [], 0
    while i < len(items):
        if items[i].state != "superseded":
            i += 1
            continue
        j = i
        while j + 1 < len(items) and items[j + 1].state == "superseded":
            j += 1
        nxt = next((c for c in items[j + 1 :] if c.state == "keep"), None)
        first = parse_label(items[i].text)
        same_label = (
            nxt is not None
            and first is not None
            and (lbl := parse_label(nxt.text)) is not None
            and (lbl.kind, lbl.key) == (first.kind, first.key)
        )
        if nxt is None or not (same_label or nxt.bold or nxt.own_change):
            orphans.append((i, j))
        i = j + 1
    return orphans
