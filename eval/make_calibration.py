"""Write eval/judge_calibration.jsonl: real answers of the main config, for human labels.

Items enter as drafts with `faithful: null`; the owner labels them and marks them validated.
Usage: python -m eval.make_calibration [--report PATH]
"""

import argparse
import json
import random
import sys
from pathlib import Path

from aneel_rag.config.settings import PROJECT_ROOT, config_hash, load_config
from eval.gate import GateError, latest_report
from eval.run_eval import CALIBRATION, chunk_texts, load_eval_config


def sample_answered(records: list[dict], n: int, seed: int) -> list[dict]:
    answered = sorted(
        (r for r in records if r["error"] is None and not r["abstained"]), key=lambda r: r["id"]
    )
    return sorted(
        random.Random(seed).sample(answered, min(n, len(answered))), key=lambda r: r["id"]
    )


def build_items(records: list[dict], texts: dict[str, str], report_name: str) -> list[dict]:
    return [
        {
            "id": f"c-{i:03d}",
            "question_id": r["id"],
            "question": r["question"],
            "answer": r["answer"],
            "contexts": [texts[c] for c in r["chunk_ids"]],
            "faithful": None,
            "status": "draft",
            "validated_by": None,
            "source_report": report_name,
        }
        for i, r in enumerate(records, start=1)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="eval report JSON (default: latest full one)")
    args = parser.parse_args()
    if CALIBRATION.exists():
        print(f"ERROR: {CALIBRATION.name} exists; it holds human labels, edit it by hand")
        return 1
    cfg, ecfg = load_config(), load_eval_config()
    try:
        if args.report:
            report = json.loads(args.report.read_text("utf-8"))
            name = args.report.name
        else:
            report = latest_report(config_hash(cfg))
            name = f"{report['date']}_{report['git_sha']}_{report['config_hash']}.json"
    except GateError as exc:
        print(f"ERROR: {exc}")
        return 1
    picked = sample_answered(
        report["pipeline"]["records"], ecfg.calibration.n, ecfg.calibration.seed
    )
    items = build_items(picked, chunk_texts(cfg), name)
    with open(CALIBRATION, "w", encoding="utf-8", newline="\n") as fh:
        for item in items:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"{len(items)} draft items -> {CALIBRATION.relative_to(PROJECT_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
