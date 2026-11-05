from typing import TypedDict

from aneel_rag.graph.schemas import AnswerSchema, FinalAnswer, Validation
from aneel_rag.retrieval.retriever import Hit


class GraphState(TypedDict, total=False):
    question: str
    trace_id: str
    retrieved: list[Hit]  # candidate pool
    reranked: list[Hit]  # the k_final hits shown to the LLM
    context_sufficient: bool
    answer: AnswerSchema | None
    validation: Validation | None
    attempts: int  # generate calls so far
    final: FinalAnswer
