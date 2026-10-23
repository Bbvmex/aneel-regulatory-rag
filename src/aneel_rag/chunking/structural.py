"""One chunk per article; long articles split along the device tree (ADR-002)."""

from collections import defaultdict
from itertools import groupby

from aneel_rag.chunking.models import Chunk
from aneel_rag.ingest.models import Unit

PATH_SEP = " > "

# A chunk part: (context units repeated for orientation, body units it covers)
Part = tuple[list[Unit], list[Unit]]


def _size(units: list[Unit]) -> int:
    return sum(len(u.text) + 1 for u in units)


def article_path(units: list[Unit]) -> str:
    """Heading path above the article (title, chapter, section), without the article label."""
    path = units[0].hierarchy_path
    cut = next((i for i, p in enumerate(path) if p.startswith("Art.")), len(path))
    return PATH_SEP.join(path[:cut])


def _render(path: str, units: list[Unit]) -> str:
    return "\n".join([path, *(u.text for u in units)] if path else [u.text for u in units])


def _split_tree(
    units: list[Unit], max_chars: int, budget_extra: int, base_ctx: list[Unit]
) -> list[Part]:
    ids = {u.id for u in units}
    children: dict[str | None, list[Unit]] = defaultdict(list)
    for unit in units:
        children[unit.parent_id if unit.parent_id in ids else None].append(unit)

    def subtree(unit: Unit) -> list[Unit]:
        return [unit] + [d for c in children[unit.id] for d in subtree(c)]

    def split(unit: Unit, ctx: list[Unit]) -> list[Part]:
        sub = subtree(unit)
        if budget_extra + _size(ctx) + _size(sub) <= max_chars or not children[unit.id]:
            return [(ctx, sub)]
        # Too long: the head becomes context of its children, which are split in turn.
        parts: list[Part] = [(ctx, [unit])]
        for child in children[unit.id]:
            parts += split(child, [*ctx, unit])
        return parts

    roots = children[None]
    parts: list[Part] = []
    for i, root in enumerate(roots):
        # Every root after the first (normally the caput) keeps the caput as context.
        parts += split(root, base_ctx or ([] if i == 0 else [roots[0]]))
    return _merge(parts, max_chars - budget_extra)


def _merge(parts: list[Part], budget: int) -> list[Part]:
    # Pack consecutive parts while the previous chunk already shows the next part's context.
    merged: list[Part] = []
    for ctx, body in parts:
        if merged:
            prev_ctx, prev_body = merged[-1]
            shown = {u.id for u in prev_ctx + prev_body}
            fits = _size(prev_ctx) + _size(prev_body) + _size(body) <= budget
            if fits and all(u.id in shown for u in ctx):
                merged[-1] = (prev_ctx, prev_body + body)
                continue
        merged.append((ctx, body))
    return merged


def _article_chunks(article_id: str, units: list[Unit], max_chars: int) -> list[Chunk]:
    path = article_path(units)
    live = [u for u in units if u.status != "revoked"]
    revoked = [u for u in units if u.status == "revoked"]
    chunks = []
    if live:
        parts = _split_tree(live, max_chars, len(path) + 1, [])
        for n, (ctx, body) in enumerate(parts):
            chunks.append(_chunk(f"structural:{article_id}:{n}", path, ctx, body, "active"))
    if revoked:
        # Revoked devices stay searchable on request; the live caput keeps them in context.
        base = [live[0]] if live and live[0].parent_id is None else []
        parts = _split_tree(revoked, max_chars, len(path) + 1, base)
        for n, (ctx, body) in enumerate(parts):
            chunks.append(_chunk(f"structural:{article_id}:rev{n}", path, ctx, body, "revoked"))
    return chunks


def _chunk(chunk_id: str, path: str, ctx: list[Unit], body: list[Unit], status) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        text=_render(path, ctx + body),
        unit_ids=[u.id for u in body],
        context_unit_ids=[u.id for u in ctx],
        article_id=body[0].article_id,
        article_ids=[body[0].article_id],
        doc_type="norm",
        status=status,
        strategy="structural",
    )


def _annex_chunk(unit: Unit) -> Chunk:
    return Chunk(
        chunk_id=f"structural:{unit.id}",
        text=_render(PATH_SEP.join(unit.hierarchy_path), [unit]),
        unit_ids=[unit.id],
        article_id=None,
        article_ids=[],
        doc_type="annex",
        status="revoked" if unit.status == "revoked" else "active",
        strategy="structural",
    )


def chunk_structural(units: list[Unit], max_chars: int) -> list[Chunk]:
    """A single device longer than max_chars is never split; its chunk may exceed the limit."""
    chunks: list[Chunk] = []
    for (doc_type, article_id), group in groupby(units, key=lambda u: (u.doc_type, u.article_id)):
        group = list(group)
        if doc_type == "annex":
            chunks += [_annex_chunk(u) for u in group]
        else:
            chunks += _article_chunks(article_id, group, max_chars)
    return chunks
