"""Metrics, judge cache and gate checked against values worked out by hand."""

import json

import pytest
from eval.gate import GateError, check, latest_report, load_thresholds
from eval.make_calibration import build_items, sample_answered
from eval.metrics import (
    abstention_rates,
    agreement,
    citation_rates,
    cohen_kappa,
    mean,
    recall_at_k,
    reciprocal_rank,
)
from eval.ragas_metrics import JudgeCache
from eval.run_eval import (
    gate_metrics,
    load_eval_config,
    pipeline_metrics,
    retrieval_metrics,
    slice_ids,
)
from eval.schema import Item

from aneel_rag.config import load_config

RANKED = [["art-1"], ["art-7", "art-8"], ["art-3"], ["art-9"]]


def test_recall_at_k_by_hand():
    expected = {"art-3", "art-8"}
    assert recall_at_k(RANKED, expected, 1) == 0
    assert recall_at_k(RANKED, expected, 2) == 0.5  # art-8 at rank 2
    assert recall_at_k(RANKED, expected, 3) == 1
    assert recall_at_k([], expected, 5) == 0
    with pytest.raises(ValueError):
        recall_at_k(RANKED, set(), 3)


def test_reciprocal_rank_by_hand():
    assert reciprocal_rank(RANKED, {"art-3"}) == pytest.approx(1 / 3)
    assert reciprocal_rank(RANKED, {"art-3", "art-8"}) == 0.5  # first hit wins
    assert reciprocal_rank(RANKED, {"art-1"}) == 1
    assert reciprocal_rank(RANKED, {"art-99"}) == 0


def test_citation_and_abstention_rates_by_hand():
    rates = citation_rates(["valid", "valid", "valid", "imprecise", "invalid"])
    assert rates == {"citations": 5, "valid": 0.6, "imprecise": 0.2, "invalid": 0.2}
    assert citation_rates([]) == {
        "citations": 0,
        "valid": None,
        "imprecise": None,
        "invalid": None,
    }
    rates = abstention_rates([False, False, True, False], [True, True, False])
    assert rates["false_abstention_rate"] == 0.25
    assert rates["abstention_accuracy"] == pytest.approx(2 / 3)
    assert mean([]) is None


def test_cohen_kappa_by_hand():
    # po = 4/5; pe = (3/5)(2/5) + (2/5)(3/5) = 0.48; kappa = 0.32 / 0.52
    a = [True, True, False, False, True]
    b = [True, False, False, False, True]
    assert cohen_kappa(a, b) == pytest.approx(0.32 / 0.52)
    assert cohen_kappa([True, False], [False, True]) == pytest.approx(-1)
    assert cohen_kappa([True, False, True], [True, False, True]) == 1
    assert cohen_kappa([True, True], [True, True]) is None  # chance agreement is 1
    with pytest.raises(ValueError):
        cohen_kappa([True], [True, False])


def test_agreement_by_hand():
    out = agreement([True, True, False, False, True], [True, False, False, False, True])
    assert out["n"] == 5
    assert out["accuracy"] == 0.8
    assert out["kappa"] == pytest.approx(0.32 / 0.52)


def _record(qid, expected, ranked, pool=None):
    return {"id": qid, "expected": expected, "ranked": ranked, "pool": pool or ranked}


def test_retrieval_metrics_by_hand():
    records = [
        _record(
            "q-1",
            {"article": {"art-3"}, "unit": {"art-3-p1"}},
            {"article": [["art-1"], ["art-3"]], "unit": [["art-1"], ["art-3", "art-3-p1"]]},
        ),
        _record(
            "q-2",
            {"article": {"art-5"}, "unit": {"art-5-inc-I", "art-5-inc-II"}},
            {"article": [["art-5"], ["art-6"]], "unit": [["art-5-inc-I"], ["art-6"]]},
            pool={"article": [["art-5"]], "unit": [["art-5-inc-I"], ["art-5-inc-II"]]},
        ),
    ]
    out = retrieval_metrics(records, [1, 2], ceiling_k=20)
    assert out["article"]["recall@1"] == 0.5  # (0 + 1) / 2
    assert out["article"]["recall@2"] == 1
    assert out["article"]["mrr"] == 0.75  # (1/2 + 1) / 2
    assert out["unit"]["recall@2"] == 0.75  # (1 + 1/2) / 2
    assert out["unit"]["pool_recall@20"] == 1  # q-2's pool holds both incisos
    assert "pool_recall@20" not in retrieval_metrics(records, [1], ceiling_k=None)["unit"]


def _item(qid, category, expected):
    return Item(
        id=qid,
        question=f"pergunta {qid}",
        category=category,
        expected_unit_ids=expected,
        reference_answer="r",
        source_unit_id=expected[0] if expected else "art-1",
        notes="" if expected else "sem resposta",
        batch=1,
        seed=1,
        generated_by="test",
    )


def test_slices_include_art2_definitions_only():
    items = [
        _item("q-1", "factual_single", ["art-2-inc-II"]),
        _item("q-2", "factual_single", ["art-20"]),  # art-20 is not art-2
        _item("q-3", "multi_article", ["art-2", "art-5"]),
    ]
    slices = slice_ids(items)
    assert slices["definitions_art2"] == {"q-1", "q-3"}
    assert slices["factual_single"] == {"q-1", "q-2"}
    assert slices["all"] == {"q-1", "q-2", "q-3"}


def _answer(qid, category, abstained, cited=(), verdicts=(), reason=None, attempts=1):
    return {
        "id": qid,
        "category": category,
        "expected": [] if category == "unanswerable" else ["art-5-p1"],
        "error": None,
        "abstained": abstained,
        "abstention_reason": reason,
        "attempts": attempts,
        "cited": list(cited),
        "verdicts": list(verdicts),
        "seconds": 10.0,
    }


def test_pipeline_metrics_by_hand():
    records = [
        _answer("q-1", "factual_single", False, ["art-5-p1-inc-I"], ["valid"]),  # descendant
        _answer("q-2", "factual_single", False, ["art-6"], ["valid", "imprecise"]),
        _answer("q-3", "multi_article", True, [], ["invalid"], "citations", attempts=2),
        _answer("q-4", "unanswerable", True, reason="insufficient_context"),
        _answer("q-5", "unanswerable", False, ["art-9"], ["valid"]),
        {"id": "q-6", "category": "unanswerable", "expected": [], "error": "Timeout", "seconds": 0},
    ]
    m = pipeline_metrics(records)
    assert m["errors"] == 1
    assert m["false_abstention_rate"] == pytest.approx(1 / 3)
    assert m["abstention_accuracy"] == 0.5  # errors are left out
    assert m["answered_citing_expected"] == pytest.approx(1 / 3)
    assert m["citation_rates"]["citations"] == 5
    assert m["citation_rates"]["valid"] == 0.6
    assert m["citation_rates"]["invalid"] == 0.2
    assert m["abstention_reasons"] == {"citations": 1, "insufficient_context": 1}
    assert m["retried"] == 1

    flat = gate_metrics([], "h", {"metrics": m}, "TBD")
    assert flat["pipeline.false_abstention_rate"] == pytest.approx(1 / 3)
    assert flat["judge.faithfulness"] is None


class FakeJudge:
    model_id = "fake-judge"

    def __init__(self):
        self.calls = 0

    def score(self, question, answer, contexts):
        self.calls += 1
        return {"faithfulness": 1.0, "answer_relevancy": 0.5}


def test_judge_cache_second_run_makes_no_calls(tmp_path):
    samples = [("q1", "a1", ["c1"]), ("q2", "a2", ["c1", "c2"])]
    judge = FakeJudge()
    first = JudgeCache(tmp_path)
    for s in samples:
        first.judge(judge, *s)
    second = JudgeCache(tmp_path)
    scores = [second.judge(judge, *s) for s in samples]
    assert judge.calls == 2
    assert (second.hits, second.misses) == (2, 0)
    assert scores[0] == {"faithfulness": 1.0, "answer_relevancy": 0.5}
    assert second.manifest_hash() == first.manifest_hash()
    # Any change to question, answer, contexts or judge model is a new key.
    base = JudgeCache.key("q", "a", ["c"], "m")
    assert base != JudgeCache.key("q", "a", ["c", "d"], "m")
    assert base != JudgeCache.key("q", "a", ["c"], "m2")


def test_gate_fails_while_thresholds_are_empty(tmp_path):
    path = tmp_path / "thresholds.yaml"
    path.write_text("thresholds: {}\n", "utf-8")
    with pytest.raises(GateError, match="no thresholds"):
        load_thresholds(path)
    with pytest.raises(GateError, match="no thresholds"):
        load_thresholds()  # the committed file is empty until the owner sets it
    path.write_text("thresholds:\n  a: {at_least: 1}\n", "utf-8")
    with pytest.raises(GateError, match="min"):
        load_thresholds(path)


def test_gate_check_min_max_and_tbd():
    report = {"gate_metrics": {"r": 0.8, "f": 0.1, "j": None}}
    assert check(report, {"r": {"min": 0.8}, "f": {"max": 0.1}}) == []
    failures = check(report, {"r": {"min": 0.9}, "f": {"max": 0.05}, "j": {"min": 0}, "x": {}})
    assert len(failures) == 4
    assert any("TBD" in f for f in failures)


def test_gate_reads_newest_full_report_of_the_config(tmp_path):
    def write(name, **extra):
        body = {"kind": "eval", "parts": {"pipeline": True}, "date": name[:10]} | extra
        (tmp_path / f"{name}.json").write_text(json.dumps(body), "utf-8")

    write("2026-11-01_aaa_cfg", tag="old")
    write("2026-11-02_bbb_cfg", tag="new")
    write("2026-11-03_ccc_cfg_partial", tag="partial")
    write("2026-11-04_ddd_other", tag="other")
    assert latest_report("cfg", tmp_path)["tag"] == "new"
    with pytest.raises(GateError):
        latest_report("missing", tmp_path)


def test_calibration_samples_only_answered_drafts():
    records = [_answer(f"q-{i}", "factual_single", i % 3 == 0) for i in range(1, 10)]
    for r in records:
        r |= {"question": "p", "answer": "a", "chunk_ids": ["c1"]}
    picked = sample_answered(records, 4, seed=1)
    assert len(picked) == 4
    assert not any(r["abstained"] for r in picked)
    assert picked == sample_answered(records, 4, seed=1)
    items = build_items(picked, {"c1": "texto"}, "report.json")
    assert {i["status"] for i in items} == {"draft"}
    assert all(i["faithful"] is None and i["validated_by"] is None for i in items)
    assert items[0]["contexts"] == ["texto"]


def test_eval_config_and_ablation_overlays_load():
    ecfg = load_eval_config()
    main = load_config()
    names = {p.stem for p in ecfg.ablations}
    assert {"dense", "hybrid", "hybrid_rerank", "fixed_chunking"} <= names
    for path in ecfg.ablations:
        variant = load_config(overlays=(path,))
        # Overlays touch retrieval, chunking or reranker length only, never the generator.
        assert variant.local_llm == main.local_llm
        assert variant.models == main.models
    fixed = load_config(overlays=("config/ablations/fixed_chunking.yaml",))
    assert fixed.chunking.strategy == "fixed"
    assert fixed.chunking.max_chars == main.chunking.max_chars  # untouched keys are kept
    assert max(ecfg.recall_ks) <= main.retrieval.k_final
