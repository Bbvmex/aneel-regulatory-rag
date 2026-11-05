"""Deterministic citation checks: policy D6 (ADR-004)."""

import re
import unicodedata
from collections import defaultdict
from collections.abc import Collection, Iterator, Mapping

from aneel_rag.graph.schemas import AnswerSchema, Citation, CitationCheck, Validation
from aneel_rag.ingest.models import Unit

# Typographic variants a model may swap when copying a quote.
_QUOTES = "\"'\u201c\u201d\u201e\u201f\u00ab\u00bb\u2018\u2019\u201a\u201b\u2032\u2033`\u00b4"
_DASHES = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"
_PUNCT = str.maketrans({c: '"' for c in _QUOTES} | {c: "-" for c in _DASHES})
_EDGE_ELLIPSIS = re.compile(r"^(?:\.\.\.\s*)+|(?:\s*\.\.\.)+$")


def normalize(text: str) -> str:
    """NFKC, casefold, unified quotes and dashes, collapsed whitespace."""
    text = unicodedata.normalize("NFKC", text).casefold().translate(_PUNCT)
    return " ".join(text.split())


def normalize_quote(quote: str) -> str:
    # Wrapping quote marks and a leading/trailing ellipsis do not change what is quoted.
    quote = normalize(quote).strip(' "')
    return _EDGE_ELLIPSIS.sub("", quote).strip(' "')


class CitationValidator:
    def __init__(self, units: Mapping[str, Unit], min_chars: int, max_chars: int):
        self.units = units
        self.min_chars = min_chars
        self.max_chars = max_chars
        self._text = {uid: normalize(u.text) for uid, u in units.items()}
        self._children: dict[str, list[str]] = defaultdict(list)
        for uid, unit in units.items():
            if unit.parent_id:
                self._children[unit.parent_id].append(uid)

    def descendants(self, unit_id: str) -> Iterator[str]:
        for child in self._children.get(unit_id, []):
            yield child
            yield from self.descendants(child)

    def check(self, citation: Citation, context_ids: Collection[str]) -> CitationCheck:
        uid = citation.unit_id
        unit = self.units.get(uid)

        def verdict(v, reason="", matched=None):
            url = unit.source_url if unit else None
            return CitationCheck(
                unit_id=uid,
                quote=citation.quote,
                verdict=v,
                reason=reason,
                matched_unit_id=matched,
                source_url=url,
            )

        if unit is None:
            return verdict("invalid", f"unit '{uid}' does not exist")
        if uid not in context_ids:
            return verdict("invalid", f"unit '{uid}' is not in the retrieved context")
        quote = normalize_quote(citation.quote)
        if not self.min_chars <= len(quote) <= self.max_chars:
            return verdict(
                "invalid",
                f"quote has {len(quote)} characters; allowed {self.min_chars}-{self.max_chars}",
            )
        if quote in self._text[uid]:
            return verdict("valid", matched=uid)
        # Citing an article (or §) for a passage of one of its devices: accepted, but flagged.
        for sub in self.descendants(uid):
            if quote in self._text[sub]:
                return verdict(
                    "imprecise", f"quote is in '{sub}'; cite the most specific unit", sub
                )
        elsewhere = next((c for c in sorted(context_ids) if quote in self._text.get(c, "")), None)
        hint = f"; it is in '{elsewhere}'" if elsewhere else ""
        return verdict("invalid", f"quote is not a verbatim passage of '{uid}'{hint}")

    def validate(self, answer: AnswerSchema, context_ids: Collection[str]) -> Validation:
        checks = [self.check(c, context_ids) for c in answer.citations]
        errors = [f"[{c.unit_id}] {c.reason}" for c in checks if c.verdict == "invalid"]
        if not answer.abstained and not answer.citations:
            errors.append("an answer that does not abstain needs at least one citation")
        return Validation(ok=not answer.abstained and not errors, checks=checks, errors=errors)
