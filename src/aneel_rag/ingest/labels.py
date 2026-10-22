"""Device labels at the start of a line: Art., §, Parágrafo único, incisos and alíneas."""

import re
from dataclasses import dataclass

DASHES = "-\u2013\u2014"

ART = re.compile(r"^Art\.\s*(\d+)\s*[º°o]?\s*(?:-\s*([A-Z])\b)?\s*[.:]?\s*")
PAR = re.compile(r"^§\s*(\d+)\s*[º°o]?\s*[.:]?\s*")
PU = re.compile(r"^Parágrafo\s+único\s*[.:\-]?\s*", re.IGNORECASE)
# "I -", "I-A -", "I - C -", "II-A:", "II-Programa" (no spaces), en/em dashes.
# A letter suffix needs its own trailing separator, so "I - A distribuidora" stays inciso I.
INC = re.compile(rf"^([IVXLC]+)(?:\s*[{DASHES}]\s*([A-Z])\s*[{DASHES}:]|\s*[{DASHES}])\s*")
AL = re.compile(r"^([a-z])\)\s*")

_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def roman_to_int(numeral: str) -> int | None:
    total = 0
    for i, ch in enumerate(numeral):
        value = _ROMAN[ch]
        if i + 1 < len(numeral) and value < _ROMAN[numeral[i + 1]]:
            total -= value
        else:
            total += value
    # Reject non-canonical spellings ("IIII", "VX") so words like "CIVIL" never parse.
    return total if int_to_roman(total) == numeral else None


def int_to_roman(value: int) -> str:
    out = []
    for n, sym in [
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ]:  # fmt: skip
        while value >= n:
            out.append(sym)
            value -= n
    return "".join(out)


@dataclass(frozen=True)
class Label:
    kind: str  # art | par | pu | inc | al
    number: int  # article/§ number, roman value, or alínea ordinal (a=1)
    suffix: str = ""  # letter suffix: Art. 48-A, inciso I-A
    raw: str = ""  # label text as written

    @property
    def key(self) -> tuple[int, str]:
        return self.number, self.suffix

    @property
    def display(self) -> str:
        if self.kind == "art":
            return f"Art. {self.number}" + (f"-{self.suffix}" if self.suffix else "")
        if self.kind == "par":
            return f"§ {self.number}º" if self.number < 10 else f"§ {self.number}"
        if self.kind == "pu":
            return "Parágrafo único"
        if self.kind == "inc":
            return int_to_roman(self.number) + (f"-{self.suffix}" if self.suffix else "")
        return f"{chr(96 + self.number)})"

    @property
    def id_part(self) -> str:
        if self.kind == "art":
            return f"art-{self.number}" + (f"-{self.suffix.lower()}" if self.suffix else "")
        if self.kind == "par":
            return f"p{self.number}"
        if self.kind == "pu":
            return "pu"
        if self.kind == "inc":
            return "inc-" + int_to_roman(self.number) + (f"-{self.suffix}" if self.suffix else "")
        return f"al-{chr(96 + self.number)}"


def parse_label(text: str) -> Label | None:
    text = text.replace("\u00a0", " ").lstrip()
    if m := ART.match(text):
        return Label("art", int(m.group(1)), m.group(2) or "", m.group(0).strip())
    if m := PAR.match(text):
        return Label("par", int(m.group(1)), "", m.group(0).strip())
    if m := PU.match(text):
        return Label("pu", 1, "", m.group(0).strip())
    if (m := INC.match(text)) and (value := roman_to_int(m.group(1))):
        return Label("inc", value, m.group(2) or "", m.group(0).strip())
    if m := AL.match(text):
        return Label("al", ord(m.group(1)) - 96, "", m.group(0).strip())
    return None


def parse_article_id(summary_id: str) -> Label | None:
    """`article23.`, `article1º`, `article371-A ` -> Label('art', ...)."""
    m = re.match(r"^article\s*(\d+)\s*[º°o]?\s*(?:-\s*([A-Za-z]))?", summary_id.strip())
    if not m:
        return None
    return Label("art", int(m.group(1)), (m.group(2) or "").upper(), summary_id)


def is_successor(prev: Label | None, cur: Label) -> bool:
    """Next label in the same list: n+1, or a letter suffix after n (I -> I-A -> I-B -> II)."""
    if prev is None:
        return cur.number == 1 and not cur.suffix
    if cur.number == prev.number:
        if not cur.suffix:
            return False
        return (not prev.suffix and cur.suffix == "A") or (
            bool(prev.suffix) and ord(cur.suffix) == ord(prev.suffix) + 1
        )
    return cur.number == prev.number + 1 and not cur.suffix
