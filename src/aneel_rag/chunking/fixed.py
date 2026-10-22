"""Fixed-size character windows with overlap; only a baseline for the chunking ablation."""

from aneel_rag.chunking.models import Chunk
from aneel_rag.ingest.models import Unit


def windows(length: int, size: int, overlap: int) -> list[tuple[int, int]]:
    if not 0 <= overlap < size:
        raise ValueError("fixed chunking needs 0 <= overlap < size")
    spans, start = [], 0
    while True:
        end = min(start + size, length)
        spans.append((start, end))
        if end >= length:
            return spans
        start += size - overlap


def _stream_chunks(name: str, units: list[Unit], size: int, overlap: int) -> list[Chunk]:
    # Units are joined in document order; offsets map each window back to the units it touches.
    text, offsets, pos = "", [], 0
    for unit in units:
        offsets.append((pos, pos + len(unit.text), unit))
        text += unit.text + "\n"
        pos = len(text)
    text = text[:-1]
    chunks = []
    for n, (start, end) in enumerate(windows(len(text), size, overlap)):
        touched = [u for s, e, u in offsets if s < end and e > start]
        articles = list(dict.fromkeys(u.article_id for u in touched if u.article_id))
        chunks.append(
            Chunk(
                chunk_id=f"fixed:{name}:{n}",
                text=text[start:end],
                unit_ids=[u.id for u in touched],
                article_id=articles[0] if articles else None,
                article_ids=articles,
                doc_type=touched[0].doc_type,
                status="revoked" if name.endswith("revoked") else "active",
                strategy="fixed",
            )
        )
    return chunks


def chunk_fixed(units: list[Unit], size: int, overlap: int) -> list[Chunk]:
    # Separate streams keep doc_type and status uniform inside a window, so filters still apply.
    streams = {
        "norm": [u for u in units if u.doc_type == "norm" and u.status != "revoked"],
        "norm-revoked": [u for u in units if u.doc_type == "norm" and u.status == "revoked"],
        "annex": [u for u in units if u.doc_type == "annex" and u.status != "revoked"],
        "annex-revoked": [u for u in units if u.doc_type == "annex" and u.status == "revoked"],
    }
    return [
        c
        for name, group in streams.items()
        if group
        for c in _stream_chunks(name, group, size, overlap)
    ]
