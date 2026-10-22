"""All retrieval modes against Qdrant :memory: with a fake embedder and reranker (no models)."""

import pytest
from qdrant_client import QdrantClient

from aneel_rag.chunking.structural import chunk_structural
from aneel_rag.config import load_config
from aneel_rag.ingest.models import Unit
from aneel_rag.retrieval.embedder import HashEmbedder
from aneel_rag.retrieval.index import index_chunks
from aneel_rag.retrieval.modes import MODES
from aneel_rag.retrieval.reranker import OverlapReranker
from aneel_rag.retrieval.retriever import Retriever

COLLECTION = "test"

# Local Qdrant ignores payload indexes and warns; the filters themselves still apply.
pytestmark = pytest.mark.filterwarnings("ignore:Payload indexes:UserWarning")


def _unit(uid, article, text, status="active", doc_type="norm", parent=None):
    return Unit(
        id=uid,
        parent_id=parent,
        article_id=article,
        kind="annex" if doc_type == "annex" else ("caput" if parent is None else "par"),
        label=uid,
        hierarchy_path=["TÍTULO I — GERAL", uid],
        text=text,
        source_anchor=f"{uid}#0",
        doc_type=doc_type,
        status=status,
    )


UNITS = [
    _unit("art-1", "art-1", "Art. 1º A tarifa social de energia elétrica beneficia baixa renda."),
    _unit("art-2", "art-2", "Art. 2º A distribuidora deve instalar o medidor na unidade."),
    _unit(
        "art-2-p1",
        "art-2",
        "§ 1º O medidor eletrônico de tarifa social era obrigatório.",
        status="revoked",
        parent="art-2",
    ),
    _unit("art-3", "art-3", "Art. 3º A suspensão do fornecimento exige notificação prévia."),
    _unit("art-4", "art-4", "Art. 4º O prazo de religação é de vinte e quatro horas."),
    _unit(
        "annex-I-cl-1",
        None,
        "CLÁUSULA PRIMEIRA: contrato de adesão sobre tarifa social e medidor.",
        doc_type="annex",
    ),
]


@pytest.fixture(scope="module")
def retriever():
    client = QdrantClient(":memory:")
    embedder = HashEmbedder()
    index_chunks(client, COLLECTION, chunk_structural(UNITS, max_chars=3000), embedder)
    return Retriever(client, COLLECTION, embedder, load_config().retrieval, OverlapReranker())


@pytest.mark.parametrize("mode", MODES)
def test_mode_ranks_the_lexical_match_first(retriever, mode):
    hits = retriever.search("tarifa social baixa renda", mode=mode)
    assert hits[0].chunk.unit_ids == ["art-1"]
    assert [h.rank for h in hits] == list(range(1, len(hits) + 1))


@pytest.mark.parametrize("mode", MODES)
def test_default_filters_exclude_revoked_and_annexes(retriever, mode):
    hits = retriever.search("tarifa social medidor contrato adesão", mode=mode, k=10)
    assert hits
    assert all(h.chunk.status != "revoked" and h.chunk.doc_type == "norm" for h in hits)


@pytest.mark.parametrize("mode", MODES)
def test_flags_include_revoked_and_annexes(retriever, mode):
    hits = retriever.search(
        "tarifa social medidor contrato adesão",
        mode=mode,
        k=10,
        include_revoked=True,
        include_annexes=True,
    )
    assert {h.chunk.status for h in hits} == {"active", "revoked"}
    assert {h.chunk.doc_type for h in hits} == {"norm", "annex"}


def test_k_limits_results(retriever):
    assert len(retriever.search("energia", mode="hybrid", k=2)) <= 2


def test_rerank_mode_needs_a_reranker(retriever):
    bare = Retriever(retriever.client, COLLECTION, retriever.embedder, retriever.cfg)
    with pytest.raises(ValueError):
        bare.search("tarifa", mode="hybrid+rerank")
