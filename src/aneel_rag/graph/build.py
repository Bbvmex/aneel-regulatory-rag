"""retrieve -> rerank -> grade_context -> (generate -> validate_citations | abstain)."""

import uuid

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from aneel_rag.chunking import load_units
from aneel_rag.config.settings import AppConfig, PromptsConfig, load_prompt
from aneel_rag.graph.nodes import Nodes
from aneel_rag.graph.schemas import FinalAnswer
from aneel_rag.graph.state import GraphState
from aneel_rag.llm.factory import get_provider
from aneel_rag.retrieval.index import (
    PROCESSED,
    check_processed,
    collection_name,
    make_client,
    make_embedder,
)
from aneel_rag.retrieval.provenance import check_index, expected_provenance
from aneel_rag.retrieval.reranker import BGEReranker
from aneel_rag.retrieval.retriever import Retriever


def build_graph(nodes: Nodes) -> CompiledStateGraph:
    graph = StateGraph(GraphState)
    for name in ("retrieve", "rerank", "grade_context", "generate", "validate_citations"):
        graph.add_node(name, getattr(nodes, name))
    graph.add_node("abstain", nodes.abstain)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "rerank")
    graph.add_edge("rerank", "grade_context")
    graph.add_conditional_edges("grade_context", nodes.after_grade, ["generate", "abstain"])
    graph.add_edge("generate", "validate_citations")
    graph.add_conditional_edges(
        "validate_citations",
        nodes.after_validation,
        {"end": END, "generate": "generate", "abstain": "abstain"},
    )
    graph.add_edge("abstain", END)
    return graph.compile()


def ask(graph: CompiledStateGraph, question: str, trace_id: str | None = None) -> FinalAnswer:
    state = graph.invoke({"question": question, "trace_id": trace_id or uuid.uuid4().hex})
    return state["final"]


def load_prompts(cfg: AppConfig) -> dict[str, str]:
    return {name: load_prompt(cfg, name) for name in PromptsConfig.model_fields}


def nodes_from_config(cfg: AppConfig) -> Nodes:
    """Real dependencies: Qdrant, local models, units.jsonl and the configured LLM."""
    check_processed(cfg)
    client, collection = make_client(), collection_name(cfg)
    # Fail on a stale index before loading any model.
    check_index(client, collection, expected_provenance(cfg))
    llm = get_provider("generator", cfg)
    reranker = None
    if cfg.retrieval.mode == "hybrid+rerank":
        reranker = BGEReranker(
            cfg.models.reranker,
            cfg.models.reranker_revision,
            cfg.embedding.rerank_max_length,
            cfg.embedding.batch_size,
        )
    retriever = Retriever(client, collection, make_embedder(cfg), cfg.retrieval, reranker)
    units = {u.id: u for u in load_units(PROCESSED / "units.jsonl")}
    return Nodes(retriever, llm, units, cfg, load_prompts(cfg))
