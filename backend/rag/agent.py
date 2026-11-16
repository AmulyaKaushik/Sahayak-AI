"""RAG agent: the fixed interface Sahayak_AI uses for document questions.

    answer(question, domain=None, scheme_id=None) -> RagAnswer

Retrieval-only grounding: if nothing similar enough is found, or the LLM
says the context doesn't contain the answer, the result is answer=None --
the model is never allowed to guess."""

import asyncio
import logging
from typing import Literal

import dspy
from pydantic import BaseModel

from rag import repository
from rag.embeddings import EmbeddingError, embed_query
from settings import settings
from supervisor.offline import named_scheme_ids
from workers.base_worker import build_lm

__all__ = ["RagAnswer", "RagSource", "answer"]

logger = logging.getLogger(__name__)


class RagSource(BaseModel):
    doc: str
    page: int | None = None


class RagAnswer(BaseModel):
    answer: str | None
    sources: list[RagSource] = []
    confidence: Literal["high", "medium", "low"] = "low"
    # True when the answer could not be looked up (service down, rate limit)
    # as opposed to answer=None because the documents genuinely don't say.
    unavailable: bool = False


class AnswerFromContext(dspy.Signature):
    """Answer the question using ONLY the numbered context passages. If the
    passages do not contain the answer, return an empty string for answer --
    never use outside knowledge and never guess. Quote numbers (ages,
    amounts, limits) exactly as written. Answer in 1-3 complete sentences
    that say what the number or fact is about (e.g. "The account matures 21
    years after it is opened.", never just "21 years"), so the answer makes
    sense without the question."""

    question: str = dspy.InputField()
    context: list[str] = dspy.InputField(desc="Numbered passages from official documents.")
    answer: str = dspy.OutputField(desc="Empty string if the context does not answer the question.")
    used_passages: list[int] = dspy.OutputField(desc="Numbers of the passages the answer relied on.")


_answer_from_context = dspy.Predict(AnswerFromContext)

_HIGH_SIMILARITY = 0.65


def _retrieve(question: str, domain: str | None, scheme_id: str | None) -> list[dict]:
    """Vector search; if the embedding service is not available, fall back to
    keyword search so documents can still be searched without it."""
    domains = [domain] if domain in ("loan", "scheme") else ["loan", "scheme"]
    hits: list[dict] = []
    try:
        query_vector = embed_query(question)
    except EmbeddingError:
        logger.warning("RAG: embedding unavailable; using keyword search", exc_info=True)
        # A scheme named in the question narrows the search (there is no
        # similarity score to tell the documents apart here).
        named = named_scheme_ids(question)
        keyword_scheme = scheme_id or (named[0] if len(named) == 1 else None)
        for d in domains:
            hits.extend(repository.search_text(d, question, keyword_scheme, settings.rag_top_k))
        hits.sort(key=lambda h: h["similarity"], reverse=True)
        return hits[: settings.rag_top_k]
    for d in domains:
        hits.extend(repository.search(d, query_vector, scheme_id, settings.rag_top_k))
    hits.sort(key=lambda h: h["similarity"], reverse=True)
    return hits[: settings.rag_top_k]


def _answer_sync(question: str, domain: str | None, scheme_id: str | None) -> RagAnswer:
    try:
        hits = _retrieve(question, domain, scheme_id)
    except Exception:
        # Database down, chunk tables missing...: this is a failure, not "not found".
        logger.warning("RAG: retrieval failed", exc_info=True)
        return RagAnswer(answer=None, unavailable=True)

    if not hits:
        return RagAnswer(answer=None)
    by_keyword = bool(hits[0].get("by_keyword"))
    if not by_keyword and hits[0]["similarity"] < settings.rag_min_similarity:
        return RagAnswer(answer=None)

    context = [
        f"[{i}] ({h['filename']}, page {h['page']}"
        + (f", {h['section']}" if h["section"] else "")
        + f") {h['content']}"
        for i, h in enumerate(hits, start=1)
    ]
    try:
        with dspy.context(lm=build_lm()):
            prediction = _answer_from_context(question=question, context=context)
    except Exception:
        logger.warning("RAG: answer generation failed", exc_info=True)
        return RagAnswer(answer=None, unavailable=True)

    text = (prediction.answer or "").strip()
    if not text:
        return RagAnswer(answer=None)

    used = {i - 1 for i in prediction.used_passages if isinstance(i, int) and 1 <= i <= len(hits)}
    cited = [hits[i] for i in sorted(used)] or hits[:1]
    sources: list[RagSource] = []
    for h in cited:
        source = RagSource(doc=h["filename"], page=h["page"])
        if source not in sources:
            sources.append(source)

    confidence = "high" if not by_keyword and hits[0]["similarity"] >= _HIGH_SIMILARITY else "medium"
    return RagAnswer(answer=text, sources=sources, confidence=confidence)


async def answer(
    question: str, domain: str | None = None, scheme_id: str | None = None
) -> RagAnswer:
    # Embedding, DB and LLM calls here are blocking; keep the event loop free.
    return await asyncio.to_thread(_answer_sync, question, domain, scheme_id)
