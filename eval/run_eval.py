"""Phase 5 evaluation: retrieval ablations, the full graph on the main config, RAGAS on request.

Only validated items count. Usage: python -m eval.run_eval [--skip-ablations] [--skip-pipeline]
[--judge]. The full graph starts its own llama-server, so the pins are checked (ADR-008).
"""

import argparse
import datetime as dt
import hashlib
import json
import statistics
import subprocess
import sys
import time
import uuid
from collections import Counter
from importlib import metadata
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from aneel_rag.chunking import Chunk
from aneel_rag.config.settings import (
    DEFAULT_CONFIG,
    PROJECT_ROOT,
    AppConfig,
    config_hash,
    corpus_sha256,
    get_secrets,
    load_config,
)
from eval.generator_pilot import covers
from eval.metrics import (
    abstention_rates,
    agreement,
    citation_rates,
    mean,
    recall_at_k,
    reciprocal_rank,
)
from eval.runtime import git_state, gpu_temp, wait_below, wait_healthy
from eval.schema import Item, load_items

EVAL_CONFIG = PROJECT_ROOT / "config" / "eval.yaml"
REPORTS = PROJECT_ROOT / "eval" / "reports"
PIPELINE_CACHE = PROJECT_ROOT / "data" / "cache" / "eval"
CALIBRATION = PROJECT_ROOT / "eval" / "judge_calibration.jsonl"
PROCESSED = PROJECT_ROOT / "data" / "processed"
LIBRARIES = ("FlagEmbedding", "torch", "qdrant-client", "langgraph", "langchain-openai", "ragas")
DEFINITIONS_ARTICLE = "art-2"  # decisions 27 and 30: definitions packed ~10 per chunk


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PipelineSettings(_Strict):
    pause_s: float
    gpu_hot_c: int
    gpu_cool_c: int
    gpu_start_below_c: int


class JudgeSettings(_Strict):
    answer_relevancy_strictness: int
    faithful_threshold: float


class CalibrationSettings(_Strict):
    n: int
    seed: int


class EvalConfig(_Strict):
    recall_ks: list[int]
    ablations: list[Path]
    pipeline: PipelineSettings
    judge: JudgeSettings
    calibration: CalibrationSettings


def load_eval_config(path: Path = EVAL_CONFIG) -> EvalConfig:
    return EvalConfig.model_validate(yaml.safe_load(path.read_text("utf-8")))


def eval_config_hash(ecfg: EvalConfig) -> str:
    canonical = json.dumps(ecfg.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]


# ---------------------------------------------------------------- retrieval


def expected_ids(item: Item, article_of: dict[str, str | None]) -> dict[str, set[str]]:
    return {
        "unit": set(item.expected_unit_ids),
        "article": {article_of[u] for u in item.expected_unit_ids if article_of.get(u)},
    }


def ranked_ids(chunks: list[Chunk]) -> dict[str, list[list[str]]]:
    return {"unit": [c.unit_ids for c in chunks], "article": [c.article_ids for c in chunks]}


def slice_ids(items: list[Item]) -> dict[str, set[str]]:
    """Answerable items per category, plus the Art. 2 definitions slice."""
    slices: dict[str, set[str]] = {"all": {i.id for i in items}}
    for item in items:
        slices.setdefault(item.category, set()).add(item.id)
    slices["definitions_art2"] = {
        i.id
        for i in items
        if any(
            u == DEFINITIONS_ARTICLE or u.startswith(DEFINITIONS_ARTICLE + "-")
            for u in i.expected_unit_ids
        )
    }
    return slices


def retrieval_metrics(
    records: list[dict], ks: list[int], ceiling_k: int | None
) -> dict[str, dict[str, float | int | None]]:
    """Per level (article, unit): recall@k, MRR and, for rerank variants, the pool ceiling."""
    out = {}
    for level in ("article", "unit"):
        m: dict[str, float | int | None] = {"n": len(records)}
        for k in ks:
            m[f"recall@{k}"] = mean(
                recall_at_k(r["ranked"][level], r["expected"][level], k) for r in records
            )
        m["mrr"] = mean(reciprocal_rank(r["ranked"][level], r["expected"][level]) for r in records)
        if ceiling_k is not None:
            m[f"pool_recall@{ceiling_k}"] = mean(
                recall_at_k(r["pool"][level], r["expected"][level], ceiling_k) for r in records
            )
        out[level] = m
    return out


def run_ablations(
    ecfg: EvalConfig, items: list[Item], article_of: dict[str, str | None]
) -> list[dict]:
    from aneel_rag.retrieval.index import collection_name, make_client, make_embedder
    from aneel_rag.retrieval.provenance import check_index, expected_provenance
    from aneel_rag.retrieval.reranker import make_reranker
    from aneel_rag.retrieval.retriever import Retriever

    answerable = [i for i in items if i.category != "unanswerable"]
    slices = slice_ids(answerable)
    client = make_client()
    variants = [(p, load_config(overlays=(p,))) for p in ecfg.ablations]
    for _, vcfg in variants:  # fail on a missing or stale index before loading any model
        check_index(client, collection_name(vcfg), expected_provenance(vcfg))

    embedder = make_embedder(load_config())  # loaded once (decision 32)
    rerankers = {}
    results = []
    for path, vcfg in variants:
        rcfg = vcfg.retrieval
        reranker = None
        if rcfg.mode == "hybrid+rerank":
            length = vcfg.embedding.rerank_max_length
            if length not in rerankers:
                rerankers[length] = make_reranker(vcfg)
            reranker = rerankers[length]
            hits0, misses0 = reranker.hits, reranker.misses
        retriever = Retriever(client, collection_name(vcfg), embedder, rcfg, reranker)
        records, seconds = [], []
        for item in answerable:
            t0 = time.perf_counter()
            pool = retriever.candidates(item.question)
            hits = retriever.rerank(item.question, pool)
            seconds.append(time.perf_counter() - t0)
            records.append(
                {
                    "id": item.id,
                    "expected": expected_ids(item, article_of),
                    "ranked": ranked_ids([h.chunk for h in hits]),
                    "pool": ranked_ids([h.chunk for h in pool]),
                    "chunk_ids": [h.chunk.chunk_id for h in hits],
                }
            )
        ceiling_k = rcfg.k_candidates if reranker else None
        by_slice = {
            name: retrieval_metrics(
                [r for r in records if r["id"] in ids], ecfg.recall_ks, ceiling_k
            )
            for name, ids in slices.items()
            if ids
        }
        result = {
            "name": Path(path).stem,
            "overlay": Path(path).as_posix(),
            "config_hash": config_hash(vcfg),
            "mode": rcfg.mode,
            "chunking": vcfg.chunking.strategy,
            "k_candidates": rcfg.k_candidates,
            "rerank_max_length": vcfg.embedding.rerank_max_length if reranker else None,
            "metrics": by_slice,
            "seconds_median": round(statistics.median(seconds), 3),
            "records": [{"id": r["id"], "chunk_ids": r["chunk_ids"]} for r in records],
        }
        if reranker:
            result["rerank_cache"] = {
                "hits": reranker.hits - hits0,
                "misses": reranker.misses - misses0,
            }
        results.append(result)
        print(f"ablation {result['name']}: {by_slice['all']['article']}", flush=True)
    return results


# ---------------------------------------------------------------- full pipeline


def pipeline_record(item: Item, state: dict, seconds: float, error: str | None) -> dict:
    rec = {
        "id": item.id,
        "category": item.category,
        "expected": list(item.expected_unit_ids),
        "seconds": round(seconds, 1),
        "error": error,
    }
    final, validation = state.get("final"), state.get("validation")
    if final is not None:
        rec |= {
            "abstained": final.abstained,
            "abstention_reason": final.abstention_reason,
            "attempts": final.attempts,
            "answer": final.answer,
            "cited": [c.matched_unit_id or c.unit_id for c in final.citations],
            # Last attempt's checks: they include the invalid citations of rejected answers.
            "verdicts": [c.verdict for c in validation.checks] if validation else [],
            "chunk_ids": [h.chunk.chunk_id for h in state.get("reranked", [])],
        }
    return rec


def pipeline_metrics(records: list[dict]) -> dict:
    ok = [r for r in records if r["error"] is None]
    answerable = [r for r in ok if r["category"] != "unanswerable"]
    unanswerable = [r for r in ok if r["category"] == "unanswerable"]
    rates = abstention_rates(
        [r["abstained"] for r in answerable], [r["abstained"] for r in unanswerable]
    )
    cited_expected = [
        not r["abstained"] and any(covers(c, r["expected"]) for c in r["cited"]) for r in answerable
    ]
    return {
        "questions": len(records),
        "errors": len(records) - len(ok),
        **rates,
        "answered_citing_expected": mean(float(x) for x in cited_expected),
        "abstention_reasons": dict(
            Counter(r["abstention_reason"] for r in ok if r["abstained"]).most_common()
        ),
        "citation_rates": citation_rates(v for r in ok for v in r["verdicts"]),
        "retried": sum(r["attempts"] > 1 for r in ok),
        "seconds_median": round(statistics.median(r["seconds"] for r in records), 1)
        if records
        else None,
    }


def cache_path(cfg_hash: str, question: str) -> Path:
    digest = hashlib.sha256(question.encode("utf-8")).hexdigest()[:24]
    return PIPELINE_CACHE / cfg_hash / f"{digest}.json"


def server_up(base_url: str) -> bool:
    import urllib.request

    health = base_url.rstrip("/").removesuffix("/v1") + "/health"
    try:
        with urllib.request.urlopen(health, timeout=3) as resp:
            return resp.status == 200
    except OSError:
        return False


def run_pipeline(cfg: AppConfig, items: list[Item], ps: PipelineSettings, sha: str) -> dict:
    """Answers are cached per (config hash, question), so an interrupted run resumes."""
    cfg_hash = config_hash(cfg)
    todo = [i for i in items if not cache_path(cfg_hash, i.question).exists()]
    cached = len(items) - len(todo)
    if todo:
        _answer(cfg, todo, ps, sha, cfg_hash)
    records, shas = [], set()
    for item in items:
        path = cache_path(cfg_hash, item.question)
        if path.exists():
            entry = json.loads(path.read_text("utf-8"))
            shas.add(entry["git_sha"])
            records.append(entry["record"] | {"id": item.id, "category": item.category})
        else:  # failed this run; reported as an error, retried on the next run
            records.append(entry_error(item))
    return {
        "records": records,
        "cache": {
            "dir": cache_path(cfg_hash, "").parent.relative_to(PROJECT_ROOT).as_posix(),
            "reused": cached,
            "new": len(items) - cached,
            "record_git_shas": sorted(shas),
        },
    }


def entry_error(item: Item) -> dict:
    return {
        "id": item.id,
        "category": item.category,
        "expected": list(item.expected_unit_ids),
        "seconds": 0.0,
        "error": "no answer (see run log)",
    }


def _answer(cfg: AppConfig, items: list[Item], ps: PipelineSettings, sha: str, cfg_hash: str):
    from aneel_rag.graph.build import build_graph, nodes_from_config  # loads torch models
    from aneel_rag.llm.server import prepare

    if cfg.llm.provider != "local":
        raise SystemExit("ERROR: the evaluation runs the pinned local generator (ADR-008)")
    base_url = get_secrets().local_llm_base_url or "http://localhost:8080/v1"
    if server_up(base_url):
        raise SystemExit(
            "ERROR: a llama-server is already running; stop it, the runner starts its own "
            "to verify the GGUF and build pins"
        )
    argv = prepare(cfg)
    graph = build_graph(nodes_from_config(cfg))
    wait_below(ps.gpu_start_below_c)
    log_path = cache_path(cfg_hash, "").parent / "server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT)
        try:
            wait_healthy(base_url, proc)
            for n, item in enumerate(items, start=1):
                if (gpu_temp() or 0) >= ps.gpu_hot_c:
                    wait_below(ps.gpu_cool_c)
                t0 = time.perf_counter()
                error, state = None, {}
                try:
                    state = graph.invoke({"question": item.question, "trace_id": uuid.uuid4().hex})
                except Exception as exc:  # recorded and retried on the next run
                    error = f"{type(exc).__name__}: {exc}"[:400]
                rec = pipeline_record(item, state, time.perf_counter() - t0, error)
                print(
                    f"[{n}/{len(items)}] {item.id} {rec['seconds']}s "
                    f"abstained={rec.get('abstained')} error={error}",
                    flush=True,
                )
                if error is None:
                    entry = {"git_sha": sha, "question": item.question, "record": rec}
                    path = cache_path(cfg_hash, item.question)
                    path.write_text(json.dumps(entry, ensure_ascii=False) + "\n", "utf-8")
                time.sleep(ps.pause_s)
        finally:
            proc.terminate()
            proc.wait(timeout=60)


# ---------------------------------------------------------------- judge


def chunk_texts(cfg: AppConfig) -> dict[str, str]:
    path = PROCESSED / f"chunks_{cfg.chunking.strategy}.jsonl"
    with open(path, encoding="utf-8") as fh:
        return {c["chunk_id"]: c["text"] for c in map(json.loads, fh)}


def load_calibration(path: Path = CALIBRATION) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def run_judge(
    cfg: AppConfig, ecfg: EvalConfig, records: list[dict], judge=None, cache=None
) -> dict:
    from eval.ragas_metrics import JudgeCache, RagasJudge

    if judge is None:
        from aneel_rag.retrieval.index import make_embedder

        judge = RagasJudge(cfg, ecfg.judge.answer_relevancy_strictness, make_embedder(cfg))
    cache = cache or JudgeCache()
    texts = chunk_texts(cfg)
    answered = [r for r in records if r["error"] is None and not r["abstained"]]
    scores = [
        cache.judge(judge, r["question"], r["answer"], [texts[c] for c in r["chunk_ids"]])
        for r in answered
    ]
    out = {
        "judge_model": judge.model_id,
        "n": len(scores),
        "faithfulness": mean(s["faithfulness"] for s in scores),
        "answer_relevancy": mean(s["answer_relevancy"] for s in scores),
    }
    labelled = [c for c in load_calibration() if c["status"] == "validated"]
    if labelled:
        threshold = ecfg.judge.faithful_threshold
        judged = [
            cache.judge(judge, c["question"], c["answer"], c["contexts"])["faithfulness"]
            >= threshold
            for c in labelled
        ]
        out["agreement"] = agreement(judged, [bool(c["faithful"]) for c in labelled])
    out["cache"] = cache.stats()
    return out


# ---------------------------------------------------------------- report


def gate_metrics(ablations: list[dict], main_hash: str, pipeline: dict | None, judge) -> dict:
    """Flat metric names that eval/thresholds.yaml can refer to; None means not measured."""
    flat: dict[str, float | None] = {}
    main = next((a for a in ablations if a["config_hash"] == main_hash), None)
    if main is not None:
        for level, m in main["metrics"]["all"].items():
            for name, value in m.items():
                if name != "n":
                    flat[f"retrieval.{level}_{name}"] = value
    if pipeline is not None:
        m = pipeline["metrics"]
        for name in ("abstention_accuracy", "false_abstention_rate", "answered_citing_expected"):
            flat[f"pipeline.{name}"] = m[name]
        for verdict in ("valid", "imprecise", "invalid"):
            flat[f"pipeline.citations_{verdict}"] = m["citation_rates"][verdict]
    for name in ("faithfulness", "answer_relevancy"):
        flat[f"judge.{name}"] = judge.get(name) if isinstance(judge, dict) else None
    return flat


def run(args: argparse.Namespace) -> Path:
    sha, dirty = git_state()
    if dirty:
        raise SystemExit("ERROR: commit first; the report records the git SHA of the code run")
    cfg, ecfg = load_config(), load_eval_config()
    all_items = load_items()
    items = [i for i in all_items if i.status == "validated"]
    from aneel_rag.chunking import load_units

    article_of = {u.id: u.article_id for u in load_units(PROCESSED / "units.jsonl")}
    main_hash = config_hash(cfg)

    ablations = [] if args.skip_ablations else run_ablations(ecfg, items, article_of)
    pipeline = None
    if not args.skip_pipeline:
        answered = run_pipeline(cfg, items, ecfg.pipeline, sha)
        question_of = {i.id: i.question for i in items}
        for r in answered["records"]:
            r["question"] = question_of[r["id"]]
        pipeline = {"metrics": pipeline_metrics(answered["records"]), **answered}
    judge: dict | str = "TBD: judge not run (no Gemini quota, ADR-005); use --judge"
    if args.judge and pipeline is not None:
        judge = run_judge(cfg, ecfg, pipeline["records"])

    report = {
        "kind": "eval",
        "date": dt.date.today().isoformat(),
        "git_sha": sha,
        "config_hash": main_hash,
        "eval_config_hash": eval_config_hash(ecfg),
        "corpus_sha256": corpus_sha256(cfg),
        "parts": {
            "ablations": bool(ablations),
            "pipeline": pipeline is not None,
            "judge": isinstance(judge, dict),
        },
        "validated_items": len(items),
        "draft_items_ignored": sum(i.status == "draft" for i in all_items),
        "rejected_items_ignored": sum(i.status == "rejected" for i in all_items),
        "items_by_category": dict(Counter(i.category for i in items)),
        "models": cfg.models.model_dump(),
        "generator": cfg.local_llm.model_dump(),
        "retrieval": cfg.retrieval.model_dump(),
        "libraries": {name: _version(name) for name in LIBRARIES},
        "eval_config": ecfg.model_dump(mode="json"),
        "gate_metrics": gate_metrics(ablations, main_hash, pipeline, judge),
        "ablations": ablations,
        "pipeline": pipeline,
        "judge": judge,
        "calibration": {
            "items": len(load_calibration()),
            "validated": sum(c["status"] == "validated" for c in load_calibration()),
        },
    }
    suffix = "" if report["parts"]["ablations"] and report["parts"]["pipeline"] else "_partial"
    stamp = f"{report['date']}_{sha}_{main_hash}{suffix}"
    REPORTS.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS / f"{stamp}.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", "utf-8")
    (REPORTS / f"{stamp}.md").write_text(render(report) + "\n", "utf-8")
    return json_path


def _version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def pct(value: float | None) -> str:
    return "TBD" if value is None else f"{100 * value:.1f}%"


def na(value: float | None) -> str:
    """Pool recall exists only for variants with a reranker."""
    return "—" if value is None else pct(value)


def num(value: float | None) -> str:
    return "TBD" if value is None else f"{value:.3f}"


def render(report: dict) -> str:
    gen, models = report["generator"], report["models"]
    lines = [
        f"# Evaluation report, {report['date']}",
        "",
        f"- git `{report['git_sha']}`, config hash `{report['config_hash']}` "
        f"(`{DEFAULT_CONFIG.relative_to(PROJECT_ROOT).as_posix()}`), "
        f"eval config hash `{report['eval_config_hash']}`",
        f"- corpus sha256 `{report['corpus_sha256']}`",
        f"- {report['validated_items']} validated items "
        f"({', '.join(f'{k} {v}' for k, v in report['items_by_category'].items())}); "
        f"{report['draft_items_ignored']} drafts and {report['rejected_items_ignored']} "
        "rejected items ignored",
        f"- generator `{gen['gguf_repo']}/{gen['gguf_file']}` ({gen['quantization']}, "
        f"sha256 `{gen['gguf_sha256'][:12]}…`), llama.cpp `{gen['llama_cpp_build']}`",
        f"- embedding `{models['embedding']}@{models['embedding_revision'][:8]}`, "
        f"reranker `{models['reranker']}@{models['reranker_revision'][:8]}`, "
        f"judge `{models['judge']}`",
        "- libraries: " + ", ".join(f"{k} {v}" for k, v in report["libraries"].items()),
        "",
    ]
    if report["ablations"]:
        lines += _render_ablations(report)
    if report["pipeline"]:
        lines += _render_pipeline(report["pipeline"])
    lines += ["## RAGAS (main configuration)", ""]
    judge = report["judge"]
    if isinstance(judge, dict):
        c = judge["cache"]
        lines += [
            f"- judge `{judge['judge_model']}`, {judge['n']} answered questions",
            f"- faithfulness {num(judge['faithfulness'])}, "
            f"answer relevancy {num(judge['answer_relevancy'])}",
            f"- judge cache `{c['dir']}`: {c['hits']} hits, {c['new_calls']} new calls, "
            f"manifest `{c['manifest_hash']}`",
        ]
        ag = judge.get("agreement")
        lines.append(
            f"- judge-human agreement on {ag['n']} validated calibration items: "
            f"accuracy {pct(ag['accuracy'])}, Cohen's kappa {num(ag['kappa'])}"
            if ag
            else "- judge-human agreement: TBD (no validated calibration items)"
        )
    else:
        lines += [f"- faithfulness and answer relevancy: {judge}", "- judge-human agreement: TBD"]
    cal = report["calibration"]
    lines += [
        f"- calibration set: {cal['items']} items, {cal['validated']} validated",
        "",
        "## Gate metrics",
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    lines += [f"| `{k}` | {num(v)} |" for k, v in report["gate_metrics"].items()]
    return "\n".join(lines)


def _render_ablations(report: dict) -> list[str]:
    ks = report["eval_config"]["recall_ks"]
    head = " | ".join(f"R@{k}" for k in ks)
    lines = [
        "## Retrieval ablations (answerable items, no LLM)",
        "",
        "Recall@k and MRR at article level (main) and unit level (secondary). "
        "Pool R@k is the recall of the candidates the reranker reorders: no reranked "
        "recall can exceed it (decision 25).",
        "",
        f"| Variant | Mode | Chunking | k_cand | Rerank max len | Article {head} | Article MRR | "
        f"Unit {head} | Unit MRR | Pool article R | Pool unit R | Median s/query |",
        "|---|---|---|---|---|" + "---|" * (2 * len(ks) + 2) + "---|---|---|",
    ]
    for a in report["ablations"]:
        art, unit = a["metrics"]["all"]["article"], a["metrics"]["all"]["unit"]
        pool_key = f"pool_recall@{a['k_candidates']}"
        main = " (main)" if a["config_hash"] == report["config_hash"] else ""
        lines.append(
            f"| {a['name']}{main} | {a['mode']} | {a['chunking']} | {a['k_candidates']} | "
            f"{a['rerank_max_length'] or '—'} | "
            + " | ".join(pct(art[f"recall@{k}"]) for k in ks)
            + f" | {num(art['mrr'])} | "
            + " | ".join(pct(unit[f"recall@{k}"]) for k in ks)
            + f" | {num(unit['mrr'])} | {na(art.get(pool_key))} | {na(unit.get(pool_key))} | "
            f"{a['seconds_median']} |"
        )
    lines += [
        "",
        "Seconds per query are for retrieval only, with reranker scores read from "
        "`data/cache/rerank.sqlite` when present (misses per variant in the JSON); they are not "
        "a latency benchmark.",
        "",
        "### Article recall@5 by slice",
        "",
    ]
    slices = [s for s in report["ablations"][0]["metrics"] if s != "all"]
    lines += ["| Variant | " + " | ".join(slices) + " |", "|---|" + "---|" * len(slices)]
    for a in report["ablations"]:
        arts = [a["metrics"][s]["article"] for s in slices]
        cells = [f"{pct(m.get('recall@5'))} (n={m['n']})" for m in arts]
        lines.append(f"| {a['name']} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "The `definitions_art2` slice (decisions 27 and 30) holds the items whose expected "
        "units are Art. 2 definitions"
        + (
            "."
            if "definitions_art2" in slices
            else ": no validated item expects one, so it "
            "is empty and decisions 27 and 30 stay open."
        )
        + " The dataset has no paraphrase tag, so decision 29 is read from the category rows.",
        "",
        "Fixed windows (1000 characters with overlap) can span two articles and list every "
        "article and unit they touch, even partly; a window counts as a hit for all of them, "
        "which favours the fixed variant at article level. Unit level is the fairer comparison.",
        "",
    ]
    return lines


def _render_pipeline(pipeline: dict) -> list[str]:
    m, c = pipeline["metrics"], pipeline["metrics"]["citation_rates"]
    cache = pipeline["cache"]
    lines = [
        "## Full pipeline (main configuration)",
        "",
        f"- {m['questions']} questions, {m['errors']} errors; answers cached in `{cache['dir']}` "
        f"({cache['reused']} reused, {cache['new']} new; produced at git "
        f"{', '.join(f'`{s}`' for s in cache['record_git_shas'])})",
        f"- abstention accuracy on unanswerable: {pct(m['abstention_accuracy'])} "
        f"(n={m['unanswerable']})",
        f"- false abstention rate on answerable: {pct(m['false_abstention_rate'])} "
        f"(n={m['answerable']})",
        f"- answerable questions answered citing an expected unit (or its ancestor or "
        f"descendant): {pct(m['answered_citing_expected'])}",
        f"- citations of the last attempt: {c['citations']}; valid {pct(c['valid'])}, "
        f"imprecise {pct(c['imprecise'])}, invalid {pct(c['invalid'])}",
        "- abstention reasons: "
        + (", ".join(f"{k} {v}" for k, v in m["abstention_reasons"].items()) or "none"),
        f"- questions retried after a citation error: {m['retried']}; "
        f"median seconds per question: {m['seconds_median']}",
        "",
        "### Per question",
        "",
        "| ID | Category | Abstained | Reason | Attempts | Verdicts | Cited | Expected |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in pipeline["records"]:
        lines.append(
            f"| {r['id']} | {r['category']} | {r.get('abstained')} | "
            f"{r.get('abstention_reason') or ''} | {r.get('attempts', '')} | "
            f"{', '.join(r.get('verdicts', []))} | {', '.join(r.get('cited', []))} | "
            f"{', '.join(r['expected'])} |"
        )
    lines.append("")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-ablations", action="store_true")
    parser.add_argument("--skip-pipeline", action="store_true")
    parser.add_argument("--judge", action="store_true", help="run RAGAS (needs judge quota)")
    path = run(parser.parse_args())
    print(f"report: {path.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
