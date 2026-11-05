"""Draft evaluation questions (ADR-007).

    python -m eval.draft_questions brief --batch 1  # seeded sample -> eval/drafts/batch-1-brief.md
    python -m eval.draft_questions add --batch 1    # eval/drafts/batch-1.jsonl -> draft items

The sample is deterministic; the questions are written from the brief by Claude Code, following
prompts/draft_questions.md. Every item enters as draft; only a human marks it validated.
"""

import argparse
import json
import random
import re
import sys
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path

from aneel_rag.chunking import load_units
from aneel_rag.config import load_config
from aneel_rag.ingest.models import Unit
from aneel_rag.retrieval.index import PROCESSED, StaleProcessedError, check_processed
from eval.schema import (
    CATEGORIES,
    DATASET,
    N_BATCHES,
    Category,
    Item,
    batch_quota,
    check_against_units,
    check_collection,
    dump_items,
    load_items,
)

DRAFTS = Path(__file__).resolve().parent / "drafts"
DEFAULT_SEED = 1000
DEFAULT_AUTHOR = "claude-code/claude-opus-5-5"
OVERSAMPLE = 2  # candidates per slot, so weak units can be skipped
MIN_CHARS = 120  # shorter units rarely carry a full rule
ARTICLE_CHARS = 2500  # cap per article in the brief; long ones are cut

DEADLINE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:\([^)]{1,40}\)\s*)?"
    r"(?:dias?|horas?|meses|m[êe]s|anos?|minutos|ciclos?)\b|R\$|\d\s*%|por cento",
    re.IGNORECASE,
)
ARTICLE_REF = re.compile(r"\bart(?:igo)?s?\.?\s*(\d+(?:-[A-Z])?)", re.IGNORECASE)
AUTHOR_FIELDS = {
    "question",
    "category",
    "expected_unit_ids",
    "reference_answer",
    "source_unit_id",
    "notes",
}


def live_norm_units(units: list[Unit]) -> list[Unit]:
    return [u for u in units if u.doc_type == "norm" and u.status != "revoked"]


def internal_refs(units: list[Unit]) -> dict[str, list[str]]:
    """article_id -> other articles of this Resolution its text mentions (may over-match)."""
    articles = {u.article_id for u in units}
    refs: dict[str, list[str]] = defaultdict(list)
    for u in units:
        for m in ARTICLE_REF.finditer(u.text):
            target = f"art-{m.group(1).lower()}"
            if target in articles and target != u.article_id and target not in refs[u.article_id]:
                refs[u.article_id].append(target)
    return refs


def pools(units: list[Unit]) -> dict[Category, list[Unit]]:
    long = [u for u in units if len(u.text) >= MIN_CHARS]
    refs = internal_refs(units)
    return {
        "factual_single": long,
        "deadline_or_value": [u for u in units if DEADLINE.search(u.text)],
        "multi_article": [u for u in units if u.kind == "caput" and u.article_id in refs],
        "unanswerable": long,
    }


def _titulo(u: Unit) -> str:
    return u.hierarchy_path[0]


def _spread(units: list[Unit], rng: random.Random) -> list[Unit]:
    """Shuffle, then alternate chapters so one long chapter does not dominate."""
    by_chapter: dict[str, list[Unit]] = defaultdict(list)
    for u in units:
        by_chapter[u.hierarchy_path[1] if len(u.hierarchy_path) > 1 else ""].append(u)
    queues = [by_chapter[k] for k in sorted(by_chapter)]
    for q in queues:
        rng.shuffle(q)
    rng.shuffle(queues)
    out = []
    while any(queues):
        for q in queues:
            if q:
                out.append(q.pop())
    return out


def _allocate(n: int, weights: Mapping[str, int]) -> dict[str, int]:
    """Largest-remainder split of n slots proportional to weights."""
    total = sum(weights.values())
    raw = {k: n * w / total for k, w in weights.items()}
    alloc = {k: int(v) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: (alloc[k] - raw[k], k))[: n - sum(alloc.values())]:
        alloc[k] += 1
    return alloc


def plan_batches(units: list[Unit], seed: int) -> dict[int, dict[Category, list[Unit]]]:
    """Disjoint candidates for every batch and category, stratified by Título."""
    rng = random.Random(seed)
    queues = {
        cat: {
            t: _spread([u for u in pool if _titulo(u) == t], rng)
            for t in sorted({_titulo(u) for u in pool})
        }
        for cat, pool in pools(units).items()
    }
    used: set[str] = set()
    plan: dict[int, dict[Category, list[Unit]]] = {}
    for batch in range(1, N_BATCHES + 1):
        plan[batch] = {}
        for cat in CATEGORIES:
            slots = batch_quota(batch)[cat] * OVERSAMPLE
            weights = {t: len(q) for t, q in queues[cat].items()}
            picked = []
            for t, n in _allocate(slots, weights).items():
                queue = queues[cat][t]
                while n and queue:
                    u = queue.pop(0)
                    # One article feeds at most one candidate, across categories and batches.
                    if u.article_id in used:
                        continue
                    used.add(u.article_id)
                    picked.append(u)
                    n -= 1
            plan[batch][cat] = picked
    return plan


def _article_text(article_id: str, by_article: Mapping[str, list[Unit]]) -> str:
    lines, size = [], 0
    for u in by_article[article_id]:
        if size > ARTICLE_CHARS:
            lines.append("[… artigo cortado; consulte data/processed/units.jsonl]")
            break
        lines.append(f"[{u.id}] {u.text}")
        size += len(u.text)
    return "\n".join(lines)


def render_brief(batch: int, seed: int, plan: dict[Category, list[Unit]], units: list[Unit]) -> str:
    by_article: dict[str, list[Unit]] = defaultdict(list)
    for u in units:
        by_article[u.article_id].append(u)
    refs = internal_refs(units)
    quota = batch_quota(batch)
    out = [
        f"# Batch {batch} brief (seed {seed})",
        "",
        "Write the questions following prompts/draft_questions.md. Quotas: "
        + ", ".join(f"{cat} {quota[cat]}" for cat in CATEGORIES)
        + f". Each category lists {OVERSAMPLE}x candidates; skip the weak ones.",
    ]
    for cat in CATEGORIES:
        out += ["", f"## {cat} ({quota[cat]} to write)"]
        for u in plan[cat]:
            out += ["", f"### {u.id} — {' > '.join(u.hierarchy_path)}", ""]
            if cat == "multi_article":
                out.append(_article_text(u.article_id, by_article))
                for target in refs[u.article_id][:3]:
                    out += ["", f"Referenced: {target}", _article_text(target, by_article)]
            else:
                out.append(f"[{u.id}] {u.text}")
                if u.parent_id:
                    parent = next(p for p in by_article[u.article_id] if p.id == u.parent_id)
                    out.append(f"(parent [{parent.id}] {parent.text[:300]})")
    return "\n".join(out) + "\n"


def build_items(rows: list[dict], batch: int, seed: int, author: str, start: int) -> list[Item]:
    """Turn authored rows into draft items; refuses rows that try to set status or ids."""
    items = []
    for i, row in enumerate(rows):
        extra = set(row) - AUTHOR_FIELDS
        if extra:
            raise ValueError(f"row {i + 1}: fields not allowed in a draft: {sorted(extra)}")
        items.append(
            Item(
                id=f"q-{start + i:03d}",
                status="draft",
                validated_by=None,
                batch=batch,
                seed=seed,
                generated_by=author,
                **row,
            )
        )
    return items


def check_quota(items: list[Item], batch: int) -> list[str]:
    counts = {cat: sum(i.category == cat for i in items) for cat in CATEGORIES}
    expected = batch_quota(batch)
    return [
        f"batch {batch}: {cat} has {counts[cat]}, expected {expected[cat]}"
        for cat in CATEGORIES
        if counts[cat] != expected[cat]
    ]


def _units() -> list[Unit]:
    check_processed(load_config())
    return load_units(PROCESSED / "units.jsonl")


def cmd_brief(batch: int, seed: int) -> int:
    units = live_norm_units(_units())
    plan = plan_batches(units, seed)[batch]
    DRAFTS.mkdir(exist_ok=True)
    path = DRAFTS / f"batch-{batch}-brief.md"
    path.write_text(render_brief(batch, seed, plan, units), encoding="utf-8", newline="\n")
    print(f"wrote {path}")
    return 0


def cmd_add(batch: int, seed: int, author: str) -> int:
    dataset = load_items()
    if any(i.batch == batch for i in dataset):
        print(f"ERROR: batch {batch} is already in {DATASET.name}", file=sys.stderr)
        return 1
    with open(DRAFTS / f"batch-{batch}.jsonl", encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    items = build_items(rows, batch, seed, author, start=len(dataset) + 1)
    units = {u.id: u for u in _units()}
    errors = (
        check_quota(items, batch)
        + check_against_units(items, units)
        + check_collection(dataset + items)
    )
    if errors:
        print("\n".join(f"ERROR: {e}" for e in errors), file=sys.stderr)
        return 1
    dump_items(dataset + items)
    print(f"added {len(items)} draft items ({items[0].id}..{items[-1].id}) to {DATASET}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("brief", "add"):
        p = sub.add_parser(name)
        p.add_argument("--batch", type=int, required=True, choices=range(1, N_BATCHES + 1))
        p.add_argument("--seed", type=int, default=DEFAULT_SEED)
        if name == "add":
            p.add_argument("--generated-by", default=DEFAULT_AUTHOR)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "brief":
            return cmd_brief(args.batch, args.seed)
        return cmd_add(args.batch, args.seed, args.generated_by)
    except StaleProcessedError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
