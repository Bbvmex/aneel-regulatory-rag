from eval.generator_pilot import covers, load_pilot, parse_speeds, sample, summarize, with_candidate
from eval.schema import load_items

from aneel_rag.config import load_config


def test_covers_accepts_ancestors_and_descendants_only():
    assert covers("art-5-p1", ["art-5-p1"])
    assert covers("art-5-p1-inc-II", ["art-5-p1"])
    assert covers("art-5", ["art-5-p1"])
    assert not covers("art-50", ["art-5"])
    assert not covers("art-5-p2", ["art-5-p1"])


def test_sample_is_stratified_and_seeded():
    items = [i for i in load_items() if i.status == "validated"]
    first = sample(items, 2, seed=1)
    assert [i.id for i in first] == [i.id for i in sample(items, 2, seed=1)]
    assert sorted({i.category for i in first}) == sorted(
        ["factual_single", "multi_article", "deadline_or_value", "unanswerable"]
    )
    assert len(first) == 8


def test_parse_speeds_splits_prompt_and_generation():
    tail = "tokens per second)\n"
    log = (
        f"prompt eval time =  1000.00 ms /   500 tokens (2.00 ms per token,   500.00 {tail}"
        f"       eval time =  2000.00 ms /    60 tokens (33.33 ms per token,    30.00 {tail}"
    )
    assert parse_speeds(log) == ([500.0], [30.0])


def _rec(category, abstained, reason=None, verdicts=(), cited=(), expected=(), attempts=1):
    return {
        "category": category,
        "abstained": abstained,
        "abstention_reason": reason,
        "verdicts": list(verdicts),
        "cited": list(cited),
        "expected": list(expected),
        "attempts": attempts,
        "error": None,
        "seconds": 10.0,
    }


def test_summarize_counts_by_hand():
    records = [
        _rec("factual_single", False, verdicts=["valid"], cited=["art-1"], expected=["art-1"]),
        _rec(
            "multi_article",
            False,
            verdicts=["valid", "invalid"],
            cited=["art-2"],
            expected=["art-2"],
            attempts=2,
        ),
        _rec("deadline_or_value", True, reason="citations", expected=["art-3"]),
        _rec("unanswerable", True, reason="insufficient_context"),
        _rec("unanswerable", True, reason="model_abstained"),
        _rec("unanswerable", False, verdicts=["valid"], cited=["art-9"]),
    ]
    records[1]["bracketed_ids"] = True
    s = summarize(records)
    assert s["answered_citing_expected"] == 2
    assert s["answered_all_citations_valid"] == 1
    assert s["false_abstentions"] == 1
    assert s["unanswerable_abstained"] == 2
    assert s["unanswerable_abstained_by_generator"] == 1
    assert s["citations"] == {"valid": 3, "imprecise": 0, "invalid": 1}
    assert s["questions_with_bracketed_ids"] == 1
    assert s["questions_retried"] == 1


def test_candidates_replace_only_the_model_fields():
    cfg, pilot = load_config(), load_pilot()
    assert pilot.candidates[0].gguf_sha256 == cfg.local_llm.gguf_sha256  # the pinned one
    _, local = with_candidate(cfg, pilot.candidates[1])
    assert local.gguf_file == pilot.candidates[1].gguf_file
    assert local.ctx_size == cfg.local_llm.ctx_size
