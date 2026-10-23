"""Graph nodes and routers; every dependency comes in through Nodes, so tests swap in fakes."""

from collections.abc import Mapping
from typing import Literal

from aneel_rag.config.settings import AppConfig
from aneel_rag.graph.citations import CitationValidator
from aneel_rag.graph.schemas import AnswerSchema, ContextGrade, FinalAnswer, Snippet
from aneel_rag.graph.state import GraphState
from aneel_rag.ingest.models import Unit
from aneel_rag.llm.provider import LLMProvider
from aneel_rag.retrieval.retriever import Hit, Retriever


def render(template: str, **values: object) -> str:
    # Plain replacement: the norm's text and prompts may hold braces or "R$".
    for key, value in values.items():
        template = template.replace("{" + key + "}", str(value))
    return template


def context_ids(hits: list[Hit]) -> set[str]:
    """Citable units: body and repeated context units of the hits shown (decision 24)."""
    return {uid for h in hits for uid in (*h.chunk.context_unit_ids, *h.chunk.unit_ids)}


def format_context(hits: list[Hit], units: Mapping[str, Unit]) -> str:
    blocks = []
    for hit in hits:
        chunk = hit.chunk
        path = " > ".join(units[chunk.unit_ids[0]].hierarchy_path)
        lines = [f"### Trecho {hit.rank}: {path}"]
        for uid in (*chunk.context_unit_ids, *chunk.unit_ids):
            unit = units[uid]
            mark = " (REVOGADO)" if unit.status == "revoked" else ""
            lines.append(f"[{uid}]{mark} {unit.text}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


class Nodes:
    def __init__(
        self,
        retriever: Retriever,
        llm: LLMProvider,
        units: Mapping[str, Unit],
        cfg: AppConfig,
        prompts: Mapping[str, str],
    ):
        self.retriever = retriever
        self.llm = llm
        self.units = units
        self.cfg = cfg
        self.prompts = prompts
        self.validator = CitationValidator(
            units, cfg.citations.min_quote_chars, cfg.citations.max_quote_chars
        )

    def retrieve(self, state: GraphState) -> GraphState:
        return {"retrieved": self.retriever.candidates(state["question"]), "attempts": 0}

    def rerank(self, state: GraphState) -> GraphState:
        return {"reranked": self.retriever.rerank(state["question"], state["retrieved"])}

    def grade_context(self, state: GraphState) -> GraphState:
        # The LLM decides sufficiency; reranker scores saturate and are never a threshold
        # (decision 31).
        if not state["reranked"]:
            return {"context_sufficient": False}
        user = self._question_and_context(state)
        grade = self.llm.structured(self.prompts["grade_context"], user, ContextGrade)
        return {"context_sufficient": grade.sufficient}

    def generate(self, state: GraphState) -> GraphState:
        citations = self.cfg.citations
        system = render(
            self.prompts["generate"],
            min_quote_chars=citations.min_quote_chars,
            max_quote_chars=citations.max_quote_chars,
        )
        user = self._question_and_context(state)
        validation = state.get("validation")
        if validation is not None and state.get("answer") is not None:
            errors = "\n".join(f"- {e}" for e in validation.errors)
            user += (
                "\n\n## Tentativa anterior rejeitada\n"
                f"{state['answer'].model_dump_json()}\n\n"
                f"Problemas nas citações:\n{errors}\n\n"
                "Corrija as citações: copie as quotes literalmente do unit citado."
            )
        answer = self.llm.structured(system, user, AnswerSchema)
        return {"answer": answer, "attempts": state.get("attempts", 0) + 1}

    def validate_citations(self, state: GraphState) -> GraphState:
        answer = state["answer"]
        validation = self.validator.validate(answer, context_ids(state["reranked"]))
        update: GraphState = {"validation": validation}
        if validation.ok:
            update["final"] = FinalAnswer(
                answer=answer.answer,
                abstained=False,
                citations=validation.checks,
                attempts=state["attempts"],
                trace_id=state["trace_id"],
            )
        return update

    def abstain(self, state: GraphState) -> GraphState:
        answer = state.get("answer")
        if not state.get("reranked"):
            reason = "no_results"
        elif not state.get("context_sufficient"):
            reason = "insufficient_context"
        elif answer is not None and answer.abstained:
            reason = "model_abstained"
        else:
            reason = "citations"
        hits = state.get("reranked") or state.get("retrieved") or []
        snippets = [
            Snippet(
                chunk_id=h.chunk.chunk_id,
                unit_ids=h.chunk.unit_ids,
                text=h.chunk.text,
                source_url=self.units[h.chunk.unit_ids[0]].source_url,
            )
            for h in hits[: self.cfg.abstention.n_snippets]
        ]
        final = FinalAnswer(
            answer=self.cfg.abstention.message,
            abstained=True,
            abstention_reason=reason,
            snippets=snippets,
            attempts=state.get("attempts", 0),
            trace_id=state["trace_id"],
        )
        return {"final": final}

    def after_grade(self, state: GraphState) -> Literal["generate", "abstain"]:
        return "generate" if state["context_sufficient"] else "abstain"

    def after_validation(self, state: GraphState) -> Literal["end", "generate", "abstain"]:
        if state["validation"].ok:
            return "end"
        if state["answer"].abstained:
            return "abstain"
        if state["attempts"] <= self.cfg.generation.max_citation_retries:
            return "generate"
        return "abstain"

    def _question_and_context(self, state: GraphState) -> str:
        context = format_context(state["reranked"], self.units)
        return f"## Pergunta\n{state['question']}\n\n## Trechos da REN 1.000/2021\n{context}"
