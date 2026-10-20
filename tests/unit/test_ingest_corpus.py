"""Properties of the full ingestion over the versioned extract (runs in CI)."""

import json
import re
from collections import Counter
from functools import cache

from aneel_rag.config import load_config
from aneel_rag.config.settings import PROJECT_ROOT
from aneel_rag.ingest import report
from aneel_rag.ingest.__main__ import write_units
from aneel_rag.ingest.html_load import FORBIDDEN, load_extract
from aneel_rag.ingest.parser import ParseResult
from aneel_rag.ingest.pipeline import parse_extract

EXTRACT = PROJECT_ROOT / "data" / "raw" / "ren1000_law_content.html"


@cache
def corpus() -> ParseResult:
    return parse_extract(load_extract(EXTRACT), load_config())


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def test_no_duplicate_ids_among_live_units():
    ids = Counter(u.id for u in corpus().units if u.status != "revoked")
    assert [k for k, v in ids.items() if v > 1] == []
    assert corpus().duplicate_ids == []


def test_no_struck_text_in_live_units():
    # A struck run that appears nowhere in the live text of the page must not reach a live unit.
    items = corpus().items
    live_page = _norm(" ".join(c.line.text(keep_struck=False) for c in items))
    struck = {
        _norm(r.text)
        for c in items
        for r in c.line.runs
        if r.struck is not None and len(_norm(r.text)) >= 25
    }
    exclusive = [s for s in struck if s not in live_page]
    assert len(exclusive) > 100  # the property is not vacuous
    live = [u for u in corpus().units if u.status != "revoked"]
    leaks = [(u.id, s[:60]) for u in live for s in exclusive if s in _norm(u.text)]
    assert leaks == []


def test_no_related_norms_leftovers():
    assert [u.id for u in corpus().units if any(f in u.text for f in FORBIDDEN)] == []


def test_counts_reconcile_with_raw_html():
    result = corpus()
    root = load_extract(EXTRACT)
    raw = len(report.CHANGE.findall(root.get_text()))
    assert sum(report.annotation_tally(result).values()) == raw
    assert sum(report.struck_tally(result).values()) == len(report._top_level(root, "s"))
    spans = root.select("span.artigo")
    articles = [u for u in result.units if u.kind == "caput"]
    superseded = len([s for s in spans if s.find_parent("s")]) - sum(
        u.status == "revoked" for u in articles
    )
    assert len(articles) - len(result.fallback_articles) + superseded == len(spans)


def test_every_article_1_to_679_is_present():
    numbers = {int(u.label.split()[1].split("-")[0]) for u in corpus().units if u.kind == "caput"}
    assert numbers == set(range(1, 680))


def test_report_has_no_blocking_problems():
    assert report.blocking_problems(corpus()) == []


def test_ingestion_is_idempotent(tmp_path):
    first, second = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    write_units(corpus().units, first)
    write_units(parse_extract(load_extract(EXTRACT), load_config()).units, second)
    assert first.read_bytes() == second.read_bytes()
    assert json.loads(first.read_text(encoding="utf-8").splitlines()[0])["id"] == "art-1"
