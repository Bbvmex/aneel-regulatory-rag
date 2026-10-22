from typing import Literal

from pydantic import BaseModel, ConfigDict

ChunkStatus = Literal["active", "revoked"]


class Chunk(BaseModel):
    """Retrieval unit: text to embed plus the citable units it covers."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    text: str
    unit_ids: list[str]  # units whose text is the chunk body (context repeats are not listed)
    article_id: str | None  # first article covered; None for annexes
    article_ids: list[str]  # every article covered (fixed windows can span several)
    doc_type: Literal["norm", "annex"]
    # Chunk-level validity: "revoked" only when every unit is revoked; fine-grained
    # status (amended, added) stays on the units.
    status: ChunkStatus
    strategy: Literal["structural", "fixed"]
