from typing import Literal

from pydantic import BaseModel, ConfigDict

ChunkStatus = Literal["active", "revoked"]


class Chunk(BaseModel):
    """Retrieval unit: text to embed plus the citable units it covers."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    text: str
    unit_ids: list[str]  # body units only, so recall metrics count each unit once
    context_unit_ids: list[str] = []  # units repeated for orientation (caput, parent § or inciso)
    article_id: str | None  # first article covered; None for annexes
    article_ids: list[str]  # every article covered (fixed windows can span several)
    doc_type: Literal["norm", "annex"]
    # Chunk-level validity: "revoked" only when every unit is revoked; fine-grained
    # status (amended, added) stays on the units.
    status: ChunkStatus
    strategy: Literal["structural", "fixed"]
