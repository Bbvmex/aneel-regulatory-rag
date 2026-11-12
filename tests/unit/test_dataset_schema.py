"""Dataset schema, draft-only authoring, seeded sampling and the versioned eval/dataset.jsonl."""

from collections import Counter
from functools import cache

import pytest
from eval.draft_questions import build_items, check_quota, plan_batches
from eval.schema import (
    CATEGORIES,
    N_BATCHES,
    TOTALS,
    Item,
    batch_quota,
    check_against_units,
    check_collection,
    load_items,
)
from pydantic import ValidationError

from aneel_rag.config import load_config
from aneel_rag.config.settings import PROJECT_ROOT
from aneel_rag.ingest.html_load import load_extract
from aneel_rag.ingest.models import Unit
from aneel_rag.ingest.pipeline import parse_extract

ROW = {
    "question": "Qual o prazo?",
    "category": "deadline_or_value",
    "expected_unit_ids": ["art-1"],
    "reference_answer": "30 dias.",
    "source_unit_id": "art-1",
    "notes": "",
}


def _item(**overrides):
    fields = {**ROW, "id": "q-001", "batch": 1, "seed": 1, "generated_by": "test", **overrides}
    return Item(**fields)


def _unit(uid, article, title="TÍTULO I", chapter="CAPÍTULO I", status="active", doc_type="norm"):
    return Unit(
        id=uid,
        parent_id=None,
        article_id=article,
        kind="caput",
        label=uid,
        hierarchy_path=[title, chapter, uid],
        text=f"Art. {uid} A distribuidora deve atender em 30 dias a solicitação do consumidor " * 2,
        source_anchor=f"{uid}#0",
        doc_type=doc_type,
        status=status,
    )


@cache
def corpus_units() -> dict[str, Unit]:
    extract = PROJECT_ROOT / "data" / "raw" / "ren1000_law_content.html"
    return {u.id: u for u in parse_extract(load_extract(extract), load_config()).units}


def test_validated_needs_validated_by():
    with pytest.raises(ValidationError, match="validated_by"):
        _item(status="validated")
    assert _item(status="validated", validated_by="hugo").status == "validated"


def test_draft_cannot_carry_validated_by():
    with pytest.raises(ValidationError, match="draft cannot"):
        _item(validated_by="hugo")


def test_unanswerable_has_no_units_and_explains_why():
    with pytest.raises(ValidationError, match="no expected units"):
        _item(category="unanswerable", notes="why")
    with pytest.raises(ValidationError, match="notes"):
        _item(category="unanswerable", expected_unit_ids=[])
    assert _item(category="unanswerable", expected_unit_ids=[], notes="why").category


def test_answerable_needs_units():
    with pytest.raises(ValidationError, match="expected_unit_ids"):
        _item(expected_unit_ids=[])


def test_every_batch_has_thirty_and_totals_match_the_plan():
    quotas = [batch_quota(b) for b in range(1, N_BATCHES + 1)]
    assert [sum(q.values()) for q in quotas] == [30, 30, 30]
    assert {cat: sum(q[cat] for q in quotas) for cat in CATEGORIES} == TOTALS


def test_authoring_cannot_write_validated():
    with pytest.raises(ValueError, match="not allowed"):
        build_items([{**ROW, "status": "validated"}], 1, 1, "test", start=1)
    with pytest.raises(ValueError, match="not allowed"):
        build_items([{**ROW, "validated_by": "someone"}], 1, 1, "test", start=1)
    (item,) = build_items([ROW], 2, 7, "author", start=31)
    assert (item.id, item.status, item.validated_by) == ("q-031", "draft", None)
    assert (item.batch, item.seed, item.generated_by) == (2, 7, "author")


def test_quota_check_reports_the_gap():
    items = build_items([ROW], 1, 1, "test", start=1)
    assert "deadline_or_value has 1, expected 7" in " ".join(check_quota(items, 1))


def test_corpus_rules():
    units = {
        u.id: u
        for u in [
            _unit("art-1", "art-1"),
            _unit("art-2", "art-2"),
            _unit("art-3", "art-3", status="revoked"),
            _unit("annex-I-1", None, doc_type="annex"),
        ]
    }
    cases = [
        (_item(expected_unit_ids=["art-9"]), "does not exist"),
        (_item(expected_unit_ids=["annex-I-1"]), "annex unit"),
        (_item(expected_unit_ids=["art-3"]), "revoked"),
        (_item(category="multi_article"), "at least two articles"),
        (_item(expected_unit_ids=["art-1", "art-2"]), "within one article"),
    ]
    for item, message in cases:
        assert message in " ".join(check_against_units([item], units))
    assert (
        check_against_units(
            [_item(category="multi_article", expected_unit_ids=["art-1", "art-2"])], units
        )
        == []
    )


def test_sampling_is_seeded_disjoint_and_stratified():
    units = [
        _unit(
            f"art-{i}",
            f"art-{i}",
            title="TÍTULO I" if i <= 300 else "TÍTULO II",
            chapter=f"CAPÍTULO {i % 7}",
        )
        for i in range(1, 401)
    ]
    plan = plan_batches(units, seed=5)
    assert plan_batches(units, seed=5) == plan
    assert plan_batches(units, seed=6) != plan
    picked = [u for batch in plan.values() for cands in batch.values() for u in cands]
    assert len({u.article_id for u in picked}) == len(picked)
    titles = Counter(u.hierarchy_path[0] for u in plan[1]["factual_single"])
    assert titles == {"TÍTULO I": 15, "TÍTULO II": 5}  # 2x the quota, split 3:1 like the pool


def test_versioned_dataset_is_consistent_with_the_corpus():
    items = load_items()
    assert check_collection(items) == []
    assert check_against_units(items, corpus_units()) == []
    assert Counter(i.category for i in items) == TOTALS
    assert all(i.status != "validated" or i.validated_by for i in items)
