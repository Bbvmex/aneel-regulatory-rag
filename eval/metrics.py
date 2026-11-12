"""Pure evaluation metrics; ranked results are lists of ID sets, best first."""

from collections import Counter
from collections.abc import Collection, Iterable, Sequence

Ranked = Sequence[Collection[str]]
VERDICTS = ("valid", "imprecise", "invalid")


def recall_at_k(ranked: Ranked, expected: Collection[str], k: int) -> float:
    """Share of the expected IDs found in the top k results."""
    if not expected:
        raise ValueError("recall needs at least one expected ID")
    found = set().union(*ranked[:k]) if ranked[:k] else set()
    return len(found & set(expected)) / len(set(expected))


def reciprocal_rank(ranked: Ranked, expected: Collection[str]) -> float:
    """1/rank of the first result holding any expected ID; 0 when none does."""
    wanted = set(expected)
    for rank, ids in enumerate(ranked, start=1):
        if wanted & set(ids):
            return 1 / rank
    return 0.0


def mean(values: Iterable[float]) -> float | None:
    values = list(values)
    return sum(values) / len(values) if values else None


def citation_rates(verdicts: Iterable[str]) -> dict[str, float | int | None]:
    counts = Counter(verdicts)
    total = sum(counts[v] for v in VERDICTS)
    rates: dict[str, float | int | None] = {"citations": total}
    for v in VERDICTS:
        rates[v] = counts[v] / total if total else None
    return rates


def abstention_rates(answerable: Sequence[bool], unanswerable: Sequence[bool]) -> dict:
    """Inputs are the `abstained` flags of each group."""
    return {
        "abstention_accuracy": mean(float(a) for a in unanswerable),
        "false_abstention_rate": mean(float(a) for a in answerable),
        "unanswerable": len(unanswerable),
        "answerable": len(answerable),
    }


def cohen_kappa(a: Sequence[bool], b: Sequence[bool]) -> float | None:
    """Chance-corrected agreement; None when chance agreement is 1 (one shared constant label)."""
    if len(a) != len(b) or not a:
        raise ValueError("kappa needs two label lists of the same, non-zero length")
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    expected = sum(
        (sum(x == c for x in a) / n) * (sum(y == c for y in b) / n) for c in (True, False)
    )
    if expected == 1:
        return None
    return (observed - expected) / (1 - expected)


def agreement(judge: Sequence[bool], human: Sequence[bool]) -> dict:
    return {
        "n": len(human),
        "accuracy": mean(float(j == h) for j, h in zip(judge, human, strict=True)),
        "kappa": cohen_kappa(judge, human) if human else None,
    }
