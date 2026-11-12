from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["valid", "imprecise", "invalid"]
AbstentionReason = Literal["no_results", "insufficient_context", "model_abstained", "citations"]


class Citation(BaseModel):
    unit_id: str = Field(description="ID of the cited unit, exactly as in the brackets")
    quote: str = Field(description="Verbatim passage of that unit's text")


class AnswerSchema(BaseModel):
    """What the generator returns; a non-abstained answer without citations fails validation."""

    answer: str
    citations: list[Citation]
    abstained: bool


class ContextGrade(BaseModel):
    sufficient: bool
    reason: str


class CitationCheck(BaseModel):
    unit_id: str
    quote: str
    verdict: Verdict
    reason: str = ""
    # Unit whose text holds the quote: the cited one, or a descendant when imprecise.
    matched_unit_id: str | None = None
    source_url: str | None = None


class Validation(BaseModel):
    ok: bool
    checks: list[CitationCheck]
    errors: list[str]


class Snippet(BaseModel):
    chunk_id: str
    unit_ids: list[str]
    text: str
    source_url: str | None


class FinalAnswer(BaseModel):
    answer: str
    abstained: bool
    abstention_reason: AbstentionReason | None = None
    citations: list[CitationCheck] = []
    snippets: list[Snippet] = []  # closest excerpts, shown when abstaining
    attempts: int = 0
    trace_id: str
