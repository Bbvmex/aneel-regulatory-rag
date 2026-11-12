"""Eval gate: fail when the report of the current config misses a threshold of eval/thresholds.yaml.

Fails explicitly while no threshold is defined. Usage: python -m eval.gate
"""

import json
import sys
from pathlib import Path

import yaml

from aneel_rag.config.settings import PROJECT_ROOT, config_hash, load_config

THRESHOLDS = PROJECT_ROOT / "eval" / "thresholds.yaml"
REPORTS = PROJECT_ROOT / "eval" / "reports"


class GateError(RuntimeError):
    pass


def load_thresholds(path: Path = THRESHOLDS) -> dict[str, dict[str, float]]:
    data = yaml.safe_load(path.read_text("utf-8")) if path.exists() else None
    thresholds = (data or {}).get("thresholds") or {}
    if not thresholds:
        raise GateError(
            f"{path.name} defines no thresholds yet: set them after reviewing the first "
            "evaluation report"
        )
    for name, rule in thresholds.items():
        if not isinstance(rule, dict) or not rule or set(rule) - {"min", "max"}:
            raise GateError(f"threshold '{name}' must be a mapping with 'min' and/or 'max'")
    return thresholds


def latest_report(cfg_hash: str, reports: Path = REPORTS) -> dict:
    """Newest full eval report for this exact config (date, then name, order)."""
    candidates = []
    for path in sorted(reports.glob(f"*_{cfg_hash}.json")):
        report = json.loads(path.read_text("utf-8"))
        if report.get("kind") == "eval" and report["parts"]["pipeline"]:
            candidates.append(report)
    if not candidates:
        raise GateError(f"no full evaluation report for config hash {cfg_hash}; run `make eval`")
    return candidates[-1]


def check(report: dict, thresholds: dict[str, dict[str, float]]) -> list[str]:
    failures = []
    metrics = report["gate_metrics"]
    for name, rule in sorted(thresholds.items()):
        if name not in metrics:
            failures.append(f"{name}: not in the report")
            continue
        value = metrics[name]
        if value is None:
            failures.append(f"{name}: not measured (TBD)")
            continue
        if "min" in rule and value < rule["min"]:
            failures.append(f"{name}: {value:.4f} < min {rule['min']}")
        if "max" in rule and value > rule["max"]:
            failures.append(f"{name}: {value:.4f} > max {rule['max']}")
    return failures


def main() -> int:
    try:
        thresholds = load_thresholds()
        report = latest_report(config_hash(load_config()))
    except GateError as exc:
        print(f"GATE FAILED: {exc}", file=sys.stderr)
        return 1
    failures = check(report, thresholds)
    tag = f"report {report['date']} git {report['git_sha']} config {report['config_hash']}"
    if failures:
        print(f"GATE FAILED ({tag}):", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(f"gate passed: {len(thresholds)} thresholds ({tag})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
