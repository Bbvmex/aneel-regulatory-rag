"""Flatten the norm HTML into lines of formatted runs, in document order.

Every <br> ends a line (single <br> also separates alíneas), headings and table rows are
lines of their own, and inline tags never insert spaces ("ca<fig></fig>put" stays "caput").
"""

import re
import unicodedata
from dataclasses import dataclass, field

from bs4 import NavigableString, Tag

INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"))
BLOCKS = {"h1", "h2", "h3", "h4", "h5", "p", "div", "li", "ul", "table"}


def clean(text: str) -> str:
    return unicodedata.normalize("NFC", text.translate(INVISIBLE))


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class Run:
    text: str
    struck: int | None = None  # document-order index of the enclosing top-level <s>
    bold: bool = False
    link_title: str | None = None  # tooltip of a.link_law: "Data da Norma: dd.mm.yyyy - ..."
    figure: str | None = None
    sep: bool = False  # synthetic separator (table cells, heading parts)

    @property
    def real(self) -> bool:
        return bool(self.text.strip()) and not self.sep


@dataclass
class Line:
    runs: list[Run] = field(default_factory=list)
    kind: str = "text"  # text | heading | row
    art_span: str | None = None  # data-summary-id of a span.artigo opening this line
    block: str | None = None  # enclosing block tag (h1, h2), used for the preamble
    index: int = 0

    def text(self, keep_struck: bool = True) -> str:
        return collapse("".join(r.text for r in self.runs if keep_struck or r.struck is None))

    @property
    def real_runs(self) -> list[Run]:
        return [r for r in self.runs if r.real]

    @property
    def all_struck(self) -> bool:
        runs = self.real_runs
        return bool(runs) and all(r.struck is not None for r in runs)

    @property
    def any_struck(self) -> bool:
        return any(r.struck is not None for r in self.real_runs)

    @property
    def struck_ids(self) -> set[int]:
        return {r.struck for r in self.real_runs if r.struck is not None}

    def links(self, keep_struck: bool = True) -> list[tuple[str, str]]:
        return [
            (collapse(r.text), r.link_title)
            for r in self.runs
            if r.link_title and (keep_struck or r.struck is None)
        ]

    def figures(self, keep_struck: bool = True) -> list[str]:
        return [r.figure for r in self.runs if r.figure and (keep_struck or r.struck is None)]


class _Walker:
    def __init__(self) -> None:
        self.lines: list[Line] = []
        self.current = Line()
        self.n_struck = 0

    def flush(self) -> None:
        if self.current.real_runs:
            self.current.index = len(self.lines)
            self.lines.append(self.current)
        self.current = Line()

    def add(self, run: Run) -> None:
        self.current.runs.append(run)

    def walk(self, node: Tag, ctx: dict) -> None:
        for child in node.children:
            if isinstance(child, NavigableString):
                if type(child) is NavigableString:
                    self.add(Run(clean(str(child)), **ctx))
                continue
            if not isinstance(child, Tag):
                continue
            self.visit(child, ctx)

    def visit(self, tag: Tag, ctx: dict) -> None:
        classes = tag.get("class", [])
        name = tag.name
        if name == "br":
            self.flush()
        elif name == "span" and "figura" in classes:
            self.add(Run(clean(tag.get_text()), figure=tag.get("data-file"), **ctx))
        elif name == "span" and "titulo" in classes:
            self.heading(tag, ctx)
        elif name == "span" and "artigo" in classes:
            if self.current.real_runs:
                self.flush()
            self.current.art_span = tag.get("data-summary-id", "")
            self.walk(tag, ctx)
        elif name == "table":
            self.flush()
            for tr in tag.find_all("tr"):
                self.current.kind = "row"
                for i, td in enumerate(tr.find_all(["td", "th"])):
                    if i:
                        self.add(Run(" | ", sep=True))
                    self.walk(td, ctx)
                self.flush()
        elif name == "s":
            inner = ctx
            if ctx["struck"] is None:
                inner = {**ctx, "struck": self.n_struck}
                self.n_struck += 1
            self.walk(tag, inner)
        elif name in ("b", "strong"):
            self.walk(tag, {**ctx, "bold": True})
        elif name == "a" and "link_law" in classes:
            self.walk(tag, {**ctx, "link_title": tag.get("data-original-title", "")})
        elif name in BLOCKS:
            self.flush()
            self.current.block = name
            self.walk(tag, ctx)
            self.flush()
        else:
            self.walk(tag, ctx)

    def heading(self, tag: Tag, ctx: dict) -> None:
        # A heading is one line; its internal <br>s separate "Seção II" from its name.
        self.flush()
        self.current.kind = "heading"
        sub = _Walker()
        sub.n_struck = self.n_struck
        sub.walk(tag, ctx)
        sub.flush()
        self.n_struck = sub.n_struck
        for i, part in enumerate(sub.lines):
            if i:
                self.add(Run(" — ", sep=True))
            self.current.runs.extend(part.runs)
        self.flush()


def segment(root: Tag) -> list[Line]:
    walker = _Walker()
    walker.walk(root, {"struck": None, "bold": False, "link_title": None})
    walker.flush()
    return walker.lines
