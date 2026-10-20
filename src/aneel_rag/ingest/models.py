from typing import Literal

from pydantic import BaseModel, ConfigDict

PARSER_VERSION = "1.0.0"

Status = Literal["active", "amended", "added", "revoked"]


class Amendment(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["amended", "added", "revoked"]
    norma: str | None
    data: str | None  # ISO date of the amending act


class Unit(BaseModel):
    """One citable device (caput, §, inciso, alínea) or annex piece."""

    id: str
    parent_id: str | None
    article_id: str | None
    kind: Literal["caput", "par", "inc", "al", "annex"]
    label: str
    hierarchy_path: list[str]
    text: str
    source_anchor: str
    source_url: str | None = None
    doc_type: Literal["norm", "annex"]
    status: Status
    amended_by: list[Amendment] = []
    notes: list[str] = []
    has_figure: bool = False
    figures: list[str] = []
    quotes_other_norm: bool = False


class Manifest(BaseModel):
    corpus_path: str
    corpus_sha256: str
    parser_version: str
    generated_on: str  # run date; lives here so units.jsonl stays byte-identical across runs
    units: int
    preamble: dict
    footer: list[str]
