"""Amendment annotations and validity notes embedded in the norm text."""

import re
from dataclasses import dataclass

# One level of nested parentheses: "(Suspensos os efeitos ... 60 (sessenta) ciclos ...)".
_BODY = r"(?:[^()]|\([^()]*\))*"
ANNOTATION = re.compile(
    rf"\(\s*(?P<kind>Redação\s+dada|Redação\s+acrescida|Revogad[oa]s?|Vide|Suspens[oa]s?)"
    rf"(?P<body>{_BODY})\)",
    re.IGNORECASE,
)
NORM_REF = re.compile(
    r"(?P<type>Resolução\s+Normativa|Resolução\s+Homologatória|Despacho|Lei|Decreto|"
    r"Medida\s+Provisória|Portaria)\s+(?:ANEEL\s+)?n[ºo°]\s*(?P<num>\d[\d.]*)\s*/\s*(?P<year>\d{4})",
    re.IGNORECASE,
)
DATE = re.compile(r"Data da Norma:\s*(\d{2})\.(\d{2})\.(\d{4})")

KINDS = {"redação dada": "amended", "redação acrescida": "added"}


@dataclass(frozen=True)
class Annotation:
    kind: str  # amended | added | revoked | note
    text: str  # full parenthetical, without the parentheses
    norma: str | None = None
    data: str | None = None  # ISO date of the amending act, from the link tooltip


def _kind(raw: str) -> str:
    raw = " ".join(raw.lower().split())
    if raw in KINDS:
        return KINDS[raw]
    return "revoked" if raw.startswith("revogad") else "note"


def _norm_and_date(body: str, links: list[tuple[str, str]]) -> tuple[str | None, str | None]:
    m = NORM_REF.search(body)
    if not m:
        return None, None
    number = m.group("num").replace(".", "")
    norma = f"{' '.join(m.group('type').split())} nº {int(number)}/{m.group('year')}"
    for text, title in links:
        if text.replace(".", "") == number and (d := DATE.search(title or "")):
            return norma, f"{d.group(3)}-{d.group(2)}-{d.group(1)}"
    return norma, None


def find(text: str, links: list[tuple[str, str]] | None = None) -> list[Annotation]:
    out = []
    for m in ANNOTATION.finditer(text):
        kind = _kind(m.group("kind"))
        inner = " ".join(m.group(0)[1:-1].split())
        norma, data = (None, None) if kind == "note" else _norm_and_date(inner, links or [])
        out.append(Annotation(kind, inner, norma, data))
    return out


def strip(text: str) -> str:
    return re.sub(r"[ \t]{2,}", " ", ANNOTATION.sub(" ", text)).strip()


def amendments(found: list[Annotation]) -> list[dict]:
    seen, out = set(), []
    for a in found:
        if a.kind == "note":
            continue
        item = {"kind": a.kind, "norma": a.norma, "data": a.data}
        key = tuple(item.values())
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def notes(found: list[Annotation]) -> list[str]:
    return list(dict.fromkeys(a.text for a in found if a.kind == "note"))
