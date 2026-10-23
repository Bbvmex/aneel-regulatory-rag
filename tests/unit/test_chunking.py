"""Chunking over the full parsed corpus (runs in CI) plus small synthetic cases."""

from collections import Counter
from functools import cache
from itertools import pairwise

import pytest

from aneel_rag.chunking import build_chunks
from aneel_rag.chunking.fixed import chunk_fixed, windows
from aneel_rag.chunking.structural import article_path, chunk_structural
from aneel_rag.config import load_config
from aneel_rag.config.settings import PROJECT_ROOT
from aneel_rag.ingest.html_load import load_extract
from aneel_rag.ingest.models import Unit
from aneel_rag.ingest.pipeline import parse_extract

EXTRACT = PROJECT_ROOT / "data" / "raw" / "ren1000_law_content.html"
CFG = load_config().chunking


@cache
def units() -> tuple[Unit, ...]:
    return tuple(parse_extract(load_extract(EXTRACT), load_config()).units)


@cache
def structural():
    return build_chunks(list(units()), CFG)


@cache
def fixed():
    return build_chunks(list(units()), CFG.model_copy(update={"strategy": "fixed"}))


def _unit(uid, parent, text, status="active", article="art-1", doc_type="norm"):
    return Unit(
        id=uid,
        parent_id=parent,
        article_id=article,
        kind="caput" if parent is None else "par",
        label=uid,
        hierarchy_path=["TÍTULO I — GERAL", "Art. 1", uid],
        text=text,
        source_anchor=f"{uid}#0",
        doc_type=doc_type,
        status=status,
    )


# --- structural, full corpus -------------------------------------------------------------


def test_every_structural_norm_chunk_has_path_and_caput():
    by_article: dict[str, list[Unit]] = {}
    for u in units():
        if u.doc_type == "norm":
            by_article.setdefault(u.article_id, []).append(u)
    chunks = [c for c in structural() if c.doc_type == "norm"]
    assert len(chunks) > 700
    for chunk in chunks:
        group = by_article[chunk.article_id]
        caput = next(u for u in group if u.parent_id is None)
        assert chunk.text.startswith(article_path(group) + "\n"), chunk.chunk_id
        assert caput.text in chunk.text, chunk.chunk_id


def test_structural_unit_ids_cover_every_unit_exactly_once():
    ids = [i for c in structural() for i in c.unit_ids]
    assert [k for k, v in Counter(ids).items() if v > 1] == []
    assert set(ids) == {u.id for u in units()}


def test_context_units_are_listed_apart_from_the_body():
    text = {u.id: u.text for u in units()}
    for c in structural():
        assert not set(c.context_unit_ids) & set(c.unit_ids), c.chunk_id
        assert all(text[i] in c.text for i in c.context_unit_ids), c.chunk_id
    assert all(c.context_unit_ids == [] for c in fixed())


def test_split_article_pieces_carry_caput_as_context():
    first, *rest = [c for c in structural() if c.article_id == "art-2" and c.status == "active"]
    assert "art-2" in first.unit_ids and first.context_unit_ids == []
    assert rest and all(c.context_unit_ids[0] == "art-2" for c in rest)


def test_long_articles_are_split_within_budget():
    art2 = [c for c in structural() if c.article_id == "art-2"]
    assert len(art2) > 1
    oversized = [c for c in structural() if len(c.text) > CFG.max_chars]
    # Only a single device longer than the budget may exceed it.
    assert all(len(c.unit_ids) == 1 for c in oversized)


def test_chunk_status_and_doc_type_are_uniform():
    status = {u.id: u.status for u in units()}
    doc_type = {u.id: u.doc_type for u in units()}
    for c in structural() + fixed():
        assert {doc_type[i] for i in c.unit_ids} == {c.doc_type}, c.chunk_id
        assert ({status[i] for i in c.unit_ids} == {"revoked"}) == (c.status == "revoked")


# --- structural, synthetic ---------------------------------------------------------------


def test_split_repeats_head_as_context_and_packs_siblings():
    caput = _unit("art-1", None, "Art. 1º Caput.")
    pars = [_unit(f"art-1-p{i}", "art-1", f"§ {i}º " + "x" * 40) for i in range(1, 5)]
    chunks = chunk_structural([caput, *pars], max_chars=140)
    assert [c.unit_ids for c in chunks] == [
        ["art-1", "art-1-p1", "art-1-p2"],
        ["art-1-p3", "art-1-p4"],
    ]
    assert all(c.text.startswith("TÍTULO I — GERAL\nArt. 1º Caput.") for c in chunks)
    assert [c.context_unit_ids for c in chunks] == [[], ["art-1"]]


def test_revoked_units_get_their_own_chunk_with_live_caput():
    caput = _unit("art-1", None, "Art. 1º Caput.")
    gone = _unit("art-1-p1", "art-1", "§ 1º Revogado.", status="revoked")
    live, rev = chunk_structural([caput, gone], max_chars=3000)
    assert (live.unit_ids, live.status) == (["art-1"], "active")
    assert (rev.unit_ids, rev.status) == (["art-1-p1"], "revoked")
    assert "Art. 1º Caput." in rev.text
    assert rev.context_unit_ids == ["art-1"]


# --- fixed -------------------------------------------------------------------------------


def test_windows_respect_size_and_overlap():
    assert windows(2500, 1000, 200) == [(0, 1000), (800, 1800), (1600, 2500)]
    assert windows(10, 1000, 200) == [(0, 10)]
    with pytest.raises(ValueError):
        windows(10, 100, 100)


def test_fixed_chunks_respect_size_overlap_and_cover_units():
    chunks = fixed()
    assert all(len(c.text) <= CFG.fixed_size for c in chunks)
    streams: dict[str, list] = {}
    for c in chunks:
        streams.setdefault(c.chunk_id.rsplit(":", 1)[0], []).append(c)
    for stream in streams.values():
        for prev, nxt in pairwise(stream):
            assert len(prev.text) == CFG.fixed_size
            assert prev.text[-CFG.fixed_overlap :] == nxt.text[: CFG.fixed_overlap]
    assert {i for c in chunks for i in c.unit_ids} == {u.id for u in units()}


def test_fixed_chunks_list_every_article_they_span():
    a = _unit("art-1", None, "a" * 30)
    b = _unit("art-2", None, "b" * 30, article="art-2")
    (only,) = chunk_fixed([a, b], size=100, overlap=10)
    assert only.article_ids == ["art-1", "art-2"]
    assert only.unit_ids == ["art-1", "art-2"]
