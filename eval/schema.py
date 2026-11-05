"""Evaluation dataset items and the rules that tie them to the parsed corpus (ADR-007)."""

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from aneel_rag.ingest.models import Unit

Category = Literal["factual_single", "multi_article", "deadline_or_value", "unanswerable"]
Status = Literal["draft", "validated", "rejected"]

CATEGORIES: tuple[Category, ...] = (
    "factual_single",
    "multi_article",
    "deadline_or_value",
    "unanswerable",
)
TOTALS: dict[Category, int] = {
    "factual_single": 30,
    "multi_article": 20,
    "deadline_or_value": 20,
    "unanswerable": 20,
}
N_BATCHES = 3
MIN_VALIDATED = 50

DATASET = Path(__file__).resolve().parent / "dataset.jsonl"


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    question: str  # PT-BR
    category: Category
    expected_unit_ids: list[str]  # most specific units holding the answer; empty if unanswerable
    reference_answer: str
    source_unit_id: str  # sampled unit the question was written from
    notes: str = ""
    status: Status = "draft"
    validated_by: str | None = None
    batch: int
    seed: int
    generated_by: str

    @model_validator(mode="after")
    def _rules(self) -> "Item":
        if self.status == "validated" and not self.validated_by:
            raise ValueError(f"{self.id}: validated items need validated_by")
        if self.status == "draft" and self.validated_by:
            raise ValueError(f"{self.id}: a draft cannot have validated_by")
        if self.category == "unanswerable":
            if self.expected_unit_ids:
                raise ValueError(f"{self.id}: unanswerable items have no expected units")
            if not self.notes:
                raise ValueError(f"{self.id}: unanswerable items explain why in notes")
        elif not self.expected_unit_ids:
            raise ValueError(f"{self.id}: answerable items need expected_unit_ids")
        return self


def batch_quota(batch: int) -> dict[Category, int]:
    """Per-batch share of TOTALS; remainders rotate across categories so every batch has 30."""
    quota = {}
    for i, (cat, total) in enumerate(TOTALS.items()):
        base, extra = divmod(total, N_BATCHES)
        quota[cat] = base + (1 if (batch - 1 - i) % N_BATCHES < extra else 0)
    return quota


def check_against_units(items: Iterable[Item], units: Mapping[str, Unit]) -> list[str]:
    """Rules that need the corpus: existing, live, non-annex units and per-category shape."""
    errors = []
    for item in items:
        if item.source_unit_id not in units:
            errors.append(f"{item.id}: source unit '{item.source_unit_id}' does not exist")
        articles = set()
        for uid in item.expected_unit_ids:
            unit = units.get(uid)
            if unit is None:
                errors.append(f"{item.id}: unit '{uid}' does not exist")
            elif unit.doc_type == "annex":
                # Deadlines are cited in the article, never in the table after Art. 679.
                errors.append(f"{item.id}: annex unit '{uid}' (annexes are out of the dataset)")
            elif unit.status == "revoked":
                errors.append(f"{item.id}: unit '{uid}' is revoked")
            else:
                articles.add(unit.article_id)
        if item.category == "multi_article" and len(articles) < 2:
            errors.append(f"{item.id}: multi_article needs units from at least two articles")
        if item.category in ("factual_single", "deadline_or_value") and len(articles) > 1:
            errors.append(f"{item.id}: {item.category} must stay within one article")
    return errors


def check_collection(items: list[Item]) -> list[str]:
    errors = []
    seen_ids, seen_questions = set(), set()
    for item in items:
        if item.id in seen_ids:
            errors.append(f"duplicate id '{item.id}'")
        key = " ".join(item.question.casefold().split())
        if key in seen_questions:
            errors.append(f"{item.id}: duplicate question")
        seen_ids.add(item.id)
        seen_questions.add(key)
    return errors


def load_items(path: Path = DATASET) -> list[Item]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return [Item.model_validate(json.loads(line)) for line in fh if line.strip()]


def dump_items(items: Iterable[Item], path: Path = DATASET) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for item in items:
            fh.write(item.model_dump_json() + "\n")
