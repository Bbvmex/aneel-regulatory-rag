from bs4 import Tag

from aneel_rag.config.settings import AppConfig
from aneel_rag.ingest import annotations as ann
from aneel_rag.ingest.html_load import page_text
from aneel_rag.ingest.parser import ParseResult, parse_lines
from aneel_rag.ingest.segment import segment
from aneel_rag.ingest.source_url import build_source_url


def _preamble(raw: dict) -> dict:
    lines = [(block, text, ann.strip(text)) for block, text in raw["lines"]]
    title = next((t for block, _, t in lines if block == "h2"), "")
    ementa = next((t for block, _, t in lines if block == "h1"), "")
    body = [t for block, _, t in lines if block not in ("h1", "h2") and t]
    found = [a for _, text, _ in lines for a in ann.find(text)]
    return {
        "title": title,
        "ementa": ementa,
        "enacting_clause": next((t for t in body if "resolve" in t), ""),
        "notes": ann.notes(found) + [t for t in body if "resolve" not in t],
    }


def parse_root(root: Tag) -> ParseResult:
    result = parse_lines(segment(root))
    result.preamble = _preamble(result.preamble)
    return result


def parse_extract(root: Tag, cfg: AppConfig) -> ParseResult:
    result = parse_root(root)
    page = page_text(root)
    for unit in result.units:
        unit.source_url = build_source_url(
            cfg.corpus.url, unit.text, page, unit.status, cfg.corpus.fragment_min_words
        )
    return result
