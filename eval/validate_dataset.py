"""python -m eval.validate_dataset: schema, corpus links and counts of eval/dataset.jsonl."""

import sys
from collections import Counter

from pydantic import ValidationError

from aneel_rag.chunking import load_units
from aneel_rag.config import load_config
from aneel_rag.retrieval.index import PROCESSED, StaleProcessedError, check_processed
from eval.schema import (
    CATEGORIES,
    DATASET,
    MIN_VALIDATED,
    check_against_units,
    check_collection,
    load_items,
)


def main() -> int:
    try:
        check_processed(load_config())
        items = load_items(DATASET)
    except (StaleProcessedError, ValidationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    units = {u.id: u for u in load_units(PROCESSED / "units.jsonl")}
    errors = check_collection(items) + check_against_units(items, units)
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)

    by_status = Counter(i.status for i in items)
    print(f"{len(items)} items: " + ", ".join(f"{s} {n}" for s, n in sorted(by_status.items())))
    for cat in CATEGORIES:
        counts = Counter(i.status for i in items if i.category == cat)
        print(f"  {cat}: " + ", ".join(f"{s} {n}" for s, n in sorted(counts.items())))
    if by_status["validated"] < MIN_VALIDATED:
        print(f"note: {by_status['validated']} validated; phase 5 wants at least {MIN_VALIDATED}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
