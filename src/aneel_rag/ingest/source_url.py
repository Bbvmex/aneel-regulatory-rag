"""Deep links to the official page via URL text fragments (#:~:text=...)."""

import re
import unicodedata
from urllib.parse import quote

DEFAULT_MIN_WORDS = 6

# Leading device labels: "Art. 23.", "Art. 23-A", "§ 1º", "Parágrafo único.", "IV -", "a)".
_LABEL = re.compile(
    r"""^\s*(?:
        art\.?\s*\d+(?:\.\d+)*\s*[º°o]?(?:\s*-\s*[a-z])?\s*[.:]?
      | §\s*\d+\s*[º°o]?\s*[.:]?
      | parágrafo\s+único\s*[.:-]?
      | [ivxlc]+\s*[-\u2013\u2014]  # hyphen, en dash, em dash
      | [a-z]\)
    )\s*""",
    re.IGNORECASE | re.VERBOSE,
)


def normalize(text: str) -> str:
    # Browsers match text fragments case-insensitively and across whitespace runs.
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def strip_label(text: str) -> str:
    return _LABEL.sub("", text, count=1).strip()


def _count(needle: str, haystack: str) -> int:
    # Overlapping count; over-counting only makes the prefix longer, never ambiguous.
    count, start = 0, haystack.find(needle)
    while start != -1:
        count += 1
        start = haystack.find(needle, start + 1)
    return count


def unique_prefix(unit_text: str, page_text: str, min_words: int = DEFAULT_MIN_WORDS) -> str | None:
    """Shortest prefix (>= min_words) of the label-stripped unit text that occurs once on the page.

    `page_text` must be the whole rendered page, struck-through text included,
    because the browser matches against everything visible.
    """
    words = strip_label(unit_text).split()
    if not words:
        return None
    haystack = normalize(page_text)
    for n in range(min(min_words, len(words)), len(words) + 1):
        prefix = " ".join(words[:n])
        occurrences = _count(normalize(prefix), haystack)
        if occurrences == 1:
            return prefix
        if occurrences == 0:
            return None
    return None


def encode_fragment_text(text: str) -> str:
    # The text-fragment syntax reserves '-', ',' and '&', so they must be escaped too.
    return quote(text, safe="").replace("-", "%2D")


def build_source_url(
    base_url: str,
    unit_text: str,
    page_text: str,
    status: str,
    min_words: int = DEFAULT_MIN_WORDS,
) -> str | None:
    """Text-fragment URL for a unit, or None when no safe link exists."""
    # Revoked text is struck through on the page; linking to it would mislead.
    if status == "revoked":
        return None
    prefix = unique_prefix(unit_text, page_text, min_words)
    if prefix is None:
        return None
    return f"{base_url}#:~:text={encode_fragment_text(prefix)}"
