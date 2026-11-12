"""RAGAS faithfulness and answer relevancy with a file cache per judged answer (ADR-005).

Judge: models.judge through the JUDGE_* endpoint; answer-relevancy embeddings: the local bge-m3.
"""

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from aneel_rag.config.settings import PROJECT_ROOT

CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "judge"


class Judge(Protocol):
    model_id: str

    def score(self, question: str, answer: str, contexts: Sequence[str]) -> dict[str, float]: ...


class JudgeCache:
    """One JSON file per (question, answer, contexts, judge model): a rerun calls no judge."""

    def __init__(self, root: Path = CACHE_DIR):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.hits = self.misses = 0
        self.used: set[str] = set()

    @staticmethod
    def key(question: str, answer: str, contexts: Sequence[str], judge_model_id: str) -> str:
        raw = json.dumps([question, answer, list(contexts), judge_model_id], ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def judge(self, judge: Judge, question: str, answer: str, contexts: Sequence[str]) -> dict:
        key = self.key(question, answer, contexts, judge.model_id)
        self.used.add(key)
        path = self.root / f"{key}.json"
        if path.exists():
            self.hits += 1
            return json.loads(path.read_text("utf-8"))["scores"]
        scores = judge.score(question, answer, contexts)
        self.misses += 1
        entry = {"judge_model_id": judge.model_id, "question": question, "scores": scores}
        path.write_text(json.dumps(entry, ensure_ascii=False) + "\n", "utf-8")
        return scores

    def manifest_hash(self) -> str:
        """Identifies the exact set of cached judgements this run read or wrote."""
        return hashlib.sha256("\n".join(sorted(self.used)).encode()).hexdigest()[:12]

    def stats(self) -> dict:
        return {
            "dir": self.root.relative_to(PROJECT_ROOT).as_posix()
            if self.root.is_relative_to(PROJECT_ROOT)
            else str(self.root),
            "hits": self.hits,
            "new_calls": self.misses,
            "manifest_hash": self.manifest_hash(),
        }


class RagasJudge:
    def __init__(self, cfg, strictness: int, embedder):
        from openai import AsyncOpenAI
        from ragas.llms import llm_factory
        from ragas.metrics.collections import AnswerRelevancy, Faithfulness

        from aneel_rag.config.settings import get_secrets
        from aneel_rag.llm.factory import MissingEndpointError

        secrets = get_secrets()
        if not (secrets.judge_base_url and secrets.judge_api_key):
            raise MissingEndpointError("no JUDGE_BASE_URL / JUDGE_API_KEY in .env")
        client = AsyncOpenAI(
            base_url=secrets.judge_base_url,
            api_key=secrets.judge_api_key,
            timeout=cfg.llm.timeout_s,
            max_retries=cfg.llm.max_retries,
        )
        self.model_id = cfg.models.judge
        llm = llm_factory(self.model_id, provider="openai", client=client)
        self.faithfulness = Faithfulness(llm=llm)
        self.relevancy = AnswerRelevancy(
            llm=llm, embeddings=_bge_embeddings(embedder), strictness=strictness
        )

    def score(self, question: str, answer: str, contexts: Sequence[str]) -> dict[str, float]:
        import asyncio

        async def both():
            faith = await self.faithfulness.ascore(
                user_input=question, response=answer, retrieved_contexts=list(contexts)
            )
            rel = await self.relevancy.ascore(user_input=question, response=answer)
            return {"faithfulness": faith.value, "answer_relevancy": rel.value}

        return asyncio.run(both())


def _bge_embeddings(embedder):
    """The retrieval embedder's dense vectors, wrapped for RAGAS (no remote embedding calls)."""
    from ragas.embeddings.base import BaseRagasEmbedding

    class BGEEmbeddings(BaseRagasEmbedding):
        def embed_text(self, text: str, **kwargs) -> list[float]:
            return list(embedder.embed_query(text).dense)

        async def aembed_text(self, text: str, **kwargs) -> list[float]:
            return self.embed_text(text)

    return BGEEmbeddings()
