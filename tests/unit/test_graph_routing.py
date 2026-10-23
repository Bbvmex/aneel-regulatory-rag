"""The four graph paths with Qdrant :memory:, fake embedder/reranker and a scripted LLM."""

import pytest
from qdrant_client import QdrantClient

from aneel_rag.chunking.structural import chunk_structural
from aneel_rag.config import load_config
from aneel_rag.graph.build import ask, build_graph, load_prompts
from aneel_rag.graph.nodes import Nodes, context_ids
from aneel_rag.graph.schemas import AnswerSchema, ContextGrade
from aneel_rag.ingest.models import Unit
from aneel_rag.llm.provider import ScriptedProvider
from aneel_rag.retrieval.embedder import HashEmbedder
from aneel_rag.retrieval.index import index_chunks
from aneel_rag.retrieval.provenance import IndexProvenance
from aneel_rag.retrieval.reranker import OverlapReranker
from aneel_rag.retrieval.retriever import Retriever

pytestmark = pytest.mark.filterwarnings("ignore:Payload indexes:UserWarning")

QUESTION = "Qual o prazo de religação da unidade consumidora?"
CFG = load_config()


def _unit(uid, article, text, parent=None):
    return Unit(
        id=uid,
        parent_id=parent,
        article_id=article,
        kind="caput" if parent is None else "par",
        label=uid,
        hierarchy_path=["TÍTULO I — GERAL", article],
        text=text,
        source_anchor=f"{uid}#0",
        source_url=f"https://example.org/#{uid}",
        doc_type="norm",
        status="active",
    )


UNITS = [
    _unit("art-1", "art-1", "Art. 1º A tarifa social de energia elétrica beneficia baixa renda."),
    _unit("art-4", "art-4", "Art. 4º A distribuidora deve religar a unidade consumidora."),
    _unit(
        "art-4-p1",
        "art-4",
        "§ 1º O prazo de religação da unidade consumidora é de vinte e quatro horas.",
        parent="art-4",
    ),
    _unit("art-5", "art-5", "Art. 5º A suspensão do fornecimento exige notificação prévia."),
    _unit("art-6", "art-6", "Art. 6º O consumidor pode pedir a vistoria do medidor."),
]

SUFFICIENT = ContextGrade(sufficient=True, reason="art-4-p1 traz o prazo")
GOOD = AnswerSchema(
    answer="O prazo de religação é de vinte e quatro horas.",
    citations=[{"unit_id": "art-4-p1", "quote": "prazo de religação da unidade consumidora"}],
    abstained=False,
)
PARAPHRASED = AnswerSchema(
    answer="Um dia.",
    citations=[{"unit_id": "art-4-p1", "quote": "a religação acontece em um dia inteiro"}],
    abstained=False,
)


@pytest.fixture(scope="module")
def retriever():
    client = QdrantClient(":memory:")
    embedder = HashEmbedder()
    stamp = IndexProvenance(corpus_sha256="a" * 64, parser_version="1.0.0", index_config_hash="x")
    index_chunks(client, "test", chunk_structural(UNITS, max_chars=3000), embedder, stamp)
    return Retriever(client, "test", embedder, CFG.retrieval, OverlapReranker())


def _run(retriever, replies):
    llm = ScriptedProvider(replies)
    nodes = Nodes(retriever, llm, {u.id: u for u in UNITS}, CFG, load_prompts(CFG))
    return ask(build_graph(nodes), QUESTION, trace_id="t-1"), llm


def _schemas(llm):
    return [schema.__name__ for _, _, schema in llm.calls]


def test_success_path(retriever):
    final, llm = _run(retriever, {ContextGrade: [SUFFICIENT], AnswerSchema: [GOOD]})
    assert not final.abstained
    assert final.attempts == 1
    assert final.trace_id == "t-1"
    assert [(c.unit_id, c.verdict) for c in final.citations] == [("art-4-p1", "valid")]
    assert final.citations[0].source_url == "https://example.org/#art-4-p1"
    assert _schemas(llm) == ["ContextGrade", "AnswerSchema"]


def test_insufficient_context_abstains_without_generating(retriever):
    grade = ContextGrade(sufficient=False, reason="nada sobre isso")
    final, llm = _run(retriever, {ContextGrade: [grade]})
    assert final.abstained
    assert final.abstention_reason == "insufficient_context"
    assert final.answer == CFG.abstention.message
    assert final.citations == []
    assert 0 < len(final.snippets) <= CFG.abstention.n_snippets
    assert final.snippets[0].unit_ids == ["art-4", "art-4-p1"]
    assert _schemas(llm) == ["ContextGrade"]


def test_citation_failure_then_retry_succeeds(retriever):
    final, llm = _run(retriever, {ContextGrade: [SUFFICIENT], AnswerSchema: [PARAPHRASED, GOOD]})
    assert not final.abstained
    assert final.attempts == 2
    assert _schemas(llm) == ["ContextGrade", "AnswerSchema", "AnswerSchema"]
    retry_prompt = llm.calls[2][1]
    assert "Tentativa anterior rejeitada" in retry_prompt
    assert "not a verbatim passage of 'art-4-p1'" in retry_prompt


def test_two_citation_failures_abstain(retriever):
    final, llm = _run(
        retriever, {ContextGrade: [SUFFICIENT], AnswerSchema: [PARAPHRASED, PARAPHRASED]}
    )
    assert final.abstained
    assert final.abstention_reason == "citations"
    assert final.attempts == 2
    assert _schemas(llm) == ["ContextGrade", "AnswerSchema", "AnswerSchema"]


def test_model_abstention_is_not_retried(retriever):
    gave_up = AnswerSchema(answer="Os trechos não trazem o prazo.", citations=[], abstained=True)
    final, llm = _run(retriever, {ContextGrade: [SUFFICIENT], AnswerSchema: [gave_up]})
    assert final.abstained
    assert final.abstention_reason == "model_abstained"
    assert _schemas(llm) == ["ContextGrade", "AnswerSchema"]


def test_context_shows_unit_ids_and_counts_context_units(retriever):
    hits = retriever.search(QUESTION)
    assert {"art-4", "art-4-p1"} <= context_ids(hits)
    _, llm = _run(retriever, {ContextGrade: [SUFFICIENT], AnswerSchema: [GOOD]})
    grade_prompt = llm.calls[0][1]
    assert QUESTION in grade_prompt
    assert "[art-4-p1] § 1º O prazo de religação" in grade_prompt
    system = llm.calls[1][0]
    assert "{min_quote_chars}" not in system
    assert f"between {CFG.citations.min_quote_chars} and" in system
