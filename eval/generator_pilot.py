"""Generator pilot (ADR-008): run local candidates through the real graph and write a report.

A short comparison to choose the generator, not an evaluation: a few validated questions per
category, one run each. Usage: python -m eval.generator_pilot [--only NAME ...]
"""

import argparse
import datetime as dt
import json
import random
import re
import statistics
import subprocess
import sys
import time
import urllib.request
import uuid
from importlib import metadata
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from aneel_rag.config.settings import (
    PROJECT_ROOT,
    AppConfig,
    LocalLLMConfig,
    config_hash,
    corpus_sha256,
    get_secrets,
    load_config,
)
from aneel_rag.llm.server import prepare
from eval.schema import Item, load_items

PILOT_CONFIG = PROJECT_ROOT / "config" / "pilots" / "generator.yaml"
REPORTS = PROJECT_ROOT / "eval" / "reports"
CATEGORIES = ("factual_single", "multi_article", "deadline_or_value", "unanswerable")
GRADE_ABSTENTIONS = {"no_results", "insufficient_context"}


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    gguf_repo: str
    gguf_file: str
    gguf_sha256: str
    quantization: str


class PilotConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    seed: int
    per_category: int
    pause_s: float
    gpu_hot_c: int
    gpu_cool_c: int
    gpu_start_below_c: int
    candidates: list[Candidate]


def load_pilot(path: Path = PILOT_CONFIG) -> PilotConfig:
    return PilotConfig.model_validate(yaml.safe_load(path.read_text("utf-8")))


def sample(items: list[Item], per_category: int, seed: int) -> list[Item]:
    rng = random.Random(seed)
    picked: list[Item] = []
    for cat in CATEGORIES:
        pool = sorted((i for i in items if i.category == cat), key=lambda i: i.id)
        picked += rng.sample(pool, min(per_category, len(pool)))
    return picked


def covers(cited: str, expected: list[str]) -> bool:
    """The expected unit itself, or one of its ancestors or descendants."""
    return any(
        cited == e or cited.startswith(e + "-") or e.startswith(cited + "-") for e in expected
    )


def parse_speeds(log: str) -> tuple[list[float], list[float]]:
    """(prompt, generation) tokens per second from llama-server timing lines."""
    prompt = [float(x) for x in re.findall(r"prompt eval time =.*?([\d.]+) tokens per second", log)]
    gen = [
        float(x) for x in re.findall(r"(?<!prompt )eval time =.*?([\d.]+) tokens per second", log)
    ]
    return prompt, gen


def summarize(records: list[dict]) -> dict:
    answerable = [r for r in records if r["category"] != "unanswerable"]
    unanswerable = [r for r in records if r["category"] == "unanswerable"]
    verdicts = [v for r in records for v in r.get("verdicts", [])]

    def answered(r: dict) -> bool:
        return r.get("abstained") is False

    return {
        "questions": len(records),
        "answerable": len(answerable),
        "answered_citing_expected": sum(
            answered(r) and any(covers(c, r["expected"]) for c in r["cited"]) for r in answerable
        ),
        "answered_all_citations_valid": sum(
            answered(r) and bool(r["verdicts"]) and set(r["verdicts"]) == {"valid"}
            for r in answerable
        ),
        "false_abstentions": sum(r.get("abstained") is True for r in answerable),
        "unanswerable": len(unanswerable),
        "unanswerable_abstained": sum(r.get("abstained") is True for r in unanswerable),
        "unanswerable_abstained_by_generator": sum(
            r.get("abstained") is True and r.get("abstention_reason") not in GRADE_ABSTENTIONS
            for r in unanswerable
        ),
        "citations": {v: verdicts.count(v) for v in ("valid", "imprecise", "invalid")},
        "questions_with_bracketed_ids": sum(r.get("bracketed_ids", False) for r in records),
        "questions_retried": sum(r.get("attempts", 0) > 1 for r in records),
        "errors": sum(r["error"] is not None for r in records),
        "seconds_median": round(statistics.median(r["seconds"] for r in records), 1),
    }


def gpu_temp() -> int | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return int(out.strip().splitlines()[0])
    except (OSError, subprocess.CalledProcessError, ValueError, IndexError):
        return None


def wait_below(limit: int) -> None:
    # The laptop overheats: never queue work on a hot GPU.
    while (t := gpu_temp()) is not None and t > limit:
        time.sleep(10)


def wait_healthy(base_url: str, proc: subprocess.Popen, timeout_s: float = 900) -> None:
    health = base_url.rstrip("/").removesuffix("/v1") + "/health"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"llama-server exited with code {proc.returncode}")
        try:
            with urllib.request.urlopen(health, timeout=5) as resp:
                if resp.status == 200:
                    return
        except OSError:
            pass
        time.sleep(5)
    raise TimeoutError("llama-server did not become healthy")


def run_question(graph, item: Item) -> dict:
    t0 = time.perf_counter()
    error, state = None, {}
    try:
        state = graph.invoke({"question": item.question, "trace_id": uuid.uuid4().hex})
    except Exception as exc:  # a crash is a pilot result too
        error = f"{type(exc).__name__}: {exc}"[:400]
    rec = {
        "id": item.id,
        "category": item.category,
        "expected": list(item.expected_unit_ids),
        "seconds": round(time.perf_counter() - t0, 1),
        "error": error,
    }
    final, validation = state.get("final"), state.get("validation")
    if validation is not None:
        rec["bracketed_ids"] = any(c.unit_id.startswith("[") for c in validation.checks)
        rec["last_validation_errors"] = validation.errors[:3]
    if final is not None:
        rec |= {
            "abstained": final.abstained,
            "abstention_reason": final.abstention_reason,
            "attempts": final.attempts,
            "verdicts": [c.verdict for c in final.citations],
            "cited": [c.matched_unit_id or c.unit_id for c in final.citations],
            "answer": final.answer,
        }
    rec["gpu_temp_after"] = gpu_temp()
    return rec


def git_state() -> tuple[str, bool]:
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
        ).stdout.strip()
    )
    return sha, dirty


def with_candidate(cfg: AppConfig, cand: Candidate) -> tuple[AppConfig, LocalLLMConfig]:
    fields = cand.model_dump(exclude={"name"})
    local = cfg.local_llm.model_copy(update=fields)
    return cfg.model_copy(update={"local_llm": local}), local


def run(pilot: PilotConfig, only: set[str] | None, out_dir: Path) -> Path:
    from aneel_rag.graph.build import build_graph, nodes_from_config  # loads torch models

    sha, dirty = git_state()
    if dirty:
        raise SystemExit("ERROR: commit first; the report records the git SHA of the code run")
    cfg = load_config()
    if cfg.llm.provider != "local":
        raise SystemExit("ERROR: the pilot needs llm.provider: local")
    items = [i for i in load_items() if i.status == "validated"]
    questions = sample(items, pilot.per_category, pilot.seed)
    base_url = get_secrets().local_llm_base_url or "http://localhost:8080/v1"
    graph = build_graph(nodes_from_config(cfg))  # same retrieval for every candidate

    stamp = f"{dt.date.today().isoformat()}_{sha}_{config_hash(cfg)}_generator-pilot"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for cand in pilot.candidates:
        if only and cand.name not in only:
            continue
        cand_cfg, local = with_candidate(cfg, cand)
        argv = prepare(cand_cfg, local)
        wait_below(pilot.gpu_start_below_c)
        log_path = out_dir / f"{stamp}.{cand.name}.server.log"
        with log_path.open("w", encoding="utf-8") as log:
            proc = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT)
            try:
                wait_healthy(base_url, proc)
                records = []
                for item in questions:
                    if (gpu_temp() or 0) >= pilot.gpu_hot_c:
                        wait_below(pilot.gpu_cool_c)
                    rec = run_question(graph, item)
                    records.append(rec)
                    print(cand.name, rec["id"], rec["seconds"], rec.get("abstained"), flush=True)
                    time.sleep(pilot.pause_s)
            finally:
                proc.terminate()
                proc.wait(timeout=60)
        prompt_tps, gen_tps = parse_speeds(log_path.read_text("utf-8", errors="replace"))
        log_path.unlink()  # machine paths and per-slot noise; the speeds are kept below
        summary = summarize(records) | {
            "prompt_tokens_per_s_median": round(statistics.median(prompt_tps), 1)
            if prompt_tps
            else None,
            "generation_tokens_per_s_median": round(statistics.median(gen_tps), 1)
            if gen_tps
            else None,
            "gpu_temp_max_c": max((r["gpu_temp_after"] or 0) for r in records),
        }
        results.append(
            {
                "candidate": cand.model_dump(),
                "config_hash": config_hash(cand_cfg),
                "summary": summary,
                "records": records,
            }
        )

    report = {
        "kind": "generator-pilot",
        "date": dt.date.today().isoformat(),
        "git_sha": sha,
        "config_hash": config_hash(cfg),
        "corpus_sha256": corpus_sha256(cfg),
        "llama_cpp_build": cfg.local_llm.llama_cpp_build,
        "server": cfg.local_llm.model_dump(
            exclude={"gguf_repo", "gguf_file", "gguf_sha256", "quantization"}
        ),
        "retrieval_mode": cfg.retrieval.mode,
        "validated_items": len(items),
        "draft_items_ignored": sum(i.status == "draft" for i in load_items()),
        "pilot": pilot.model_dump(exclude={"candidates"}),
        "question_ids": [q.id for q in questions],
        "libraries": {
            name: metadata.version(name)
            for name in ("langchain-openai", "langgraph", "FlagEmbedding", "torch")
        },
        "results": results,
    }
    json_path = out_dir / f"{stamp}.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    (out_dir / f"{stamp}.md").write_text(render(report), "utf-8")
    return json_path


def render(report: dict) -> str:
    lines = [
        f"# Generator pilot, {report['date']}",
        "",
        f"- git `{report['git_sha']}`, config hash `{report['config_hash']}`, "
        f"corpus sha256 `{report['corpus_sha256'][:12]}…`",
        f"- llama.cpp `{report['llama_cpp_build']}`; retrieval `{report['retrieval_mode']}`",
        f"- {len(report['question_ids'])} validated questions "
        f"({report['pilot']['per_category']} per category, seed {report['pilot']['seed']}) "
        f"of {report['validated_items']} validated; {report['draft_items_ignored']} drafts ignored",
        f"- questions: {', '.join(report['question_ids'])}",
        "",
        "A pilot to choose the generator (ADR-008), one run per candidate: it is not an "
        "evaluation and its numbers do not measure the system.",
        "",
        "| Candidate | Quant | Answered citing expected | All citations valid | "
        "False abstentions | Unanswerable abstained | Bracketed IDs | Retried | Errors | "
        "Gen tok/s | Prompt tok/s | Median s/question | Max GPU °C |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for res in report["results"]:
        s, c = res["summary"], res["candidate"]
        lines.append(
            f"| {c['name']} | {c['quantization']} | "
            f"{s['answered_citing_expected']}/{s['answerable']} | "
            f"{s['answered_all_citations_valid']}/{s['answerable']} | "
            f"{s['false_abstentions']} | {s['unanswerable_abstained']}/{s['unanswerable']} | "
            f"{s['questions_with_bracketed_ids']} | {s['questions_retried']} | {s['errors']} | "
            f"{s['generation_tokens_per_s_median']} | {s['prompt_tokens_per_s_median']} | "
            f"{s['seconds_median']} | {s['gpu_temp_max_c']} |"
        )
    lines += [
        "",
        "Seconds per question include retrieval and the CPU reranker (decision 26).",
        "",
        "## Per question",
        "",
    ]
    for res in report["results"]:
        lines += [f"### {res['candidate']['name']}", ""]
        lines += ["| ID | Category | Abstained | Reason | Attempts | Verdicts | Cited |"]
        lines += ["|---|---|---|---|---|---|---|"]
        for r in res["records"]:
            lines.append(
                f"| {r['id']} | {r['category']} | {r.get('abstained')} | "
                f"{r.get('abstention_reason') or ''} | {r.get('attempts', '')} | "
                f"{', '.join(r.get('verdicts', []))} | {', '.join(r.get('cited', []))} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", help="candidate names to run")
    args = parser.parse_args()
    path = run(load_pilot(), set(args.only) if args.only else None, REPORTS)
    print(f"report: {path.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
