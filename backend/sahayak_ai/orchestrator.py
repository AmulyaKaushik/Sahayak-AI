"""Sahayak_AI orchestrator: router -> agents -> refiner. No business logic of
its own; it only calls each agent through its one fixed function and passes
data in and out."""

import asyncio
import logging
import re

from eligibility_agent import agent as eligibility_agent
from eligibility_agent.agent import EligibilityOutput
from rag import agent as rag_agent
from sahayak_ai import refiner, router
from sahayak_ai.models import AgentOutput, SahayakResponse, SubTask

logger = logging.getLogger(__name__)

ERROR_TEXT = "Sorry, I had trouble with that. Please try again."

# Credentials are never needed and must not reach the LLMs, the profile or logs.
_SECRET = re.compile(
    r"\b(otp|one[- ]time password|pin|cvv|cvc|password|passcode|card number)\b|"
    r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b",
    re.IGNORECASE,
)
SECRET_REPLY = (
    "Please do not share your PIN, OTP, password or card details here. "
    "I never need them, and no bank will ask for them. I have not saved what you sent."
)


async def _run_subtask(
    subtask: SubTask, customer_id: str, session_id: str, original_text: str
) -> AgentOutput:
    if subtask.agent == "eligibility":
        output = await eligibility_agent.check(
            customer_id, session_id, subtask.text, subtask.scheme_id, subtask.has_question,
            facts_text=original_text,
        )
        return AgentOutput(agent="eligibility", eligibility=output)

    answer = await rag_agent.answer(subtask.text, scheme_id=subtask.scheme_id)
    return AgentOutput(agent="rag", rag=answer)


async def handle_message(
    customer_id: str, session_id: str, text: str, language: str
) -> SahayakResponse:
    if _SECRET.search(text):
        return SahayakResponse(
            reply_text=SECRET_REPLY,
            display_text=SECRET_REPLY,
            language=language,
            turn_type="acknowledgment",
        )

    active_scheme_id = await asyncio.to_thread(eligibility_agent.active_scheme_id, session_id)
    plan = await router.route(text, active_scheme_id)

    # Eligibility is the single writer of session context, so there is at
    # most one of it per plan; it is independent of RAG, so they run together.
    eligibility_tasks = [t for t in plan.subtasks if t.agent == "eligibility"][:1]
    rag_tasks = [t for t in plan.subtasks if t.agent == "rag"]
    ordered = sorted(
        eligibility_tasks + rag_tasks, key=lambda t: plan.subtasks.index(t)
    )

    settled = await asyncio.gather(
        *(_run_subtask(t, customer_id, session_id, text) for t in ordered), return_exceptions=True
    )

    outputs: list[AgentOutput] = []
    for subtask, result in zip(ordered, settled):
        if isinstance(result, BaseException):
            logger.warning(
                "Sahayak_AI: %s sub-task failed", subtask.agent, exc_info=(type(result), result, result.__traceback__)
            )
            if subtask.agent == "eligibility":
                result = AgentOutput(
                    agent="eligibility",
                    eligibility=EligibilityOutput(
                        reply_text=ERROR_TEXT, turn_type="acknowledgment", needs_clarification=True
                    ),
                )
            else:
                result = AgentOutput(agent="rag", rag=rag_agent.RagAnswer(answer=None, unavailable=True))
        outputs.append(result)

    refined = await refiner.refine(outputs, language)

    eligibility = next((o.eligibility for o in outputs if o.eligibility), None)
    rag = next((o.rag for o in outputs if o.rag), None)
    results = eligibility.results if eligibility else []

    return SahayakResponse(
        reply_text=refined.speech_text,
        display_text=refined.display_text,
        language=language,
        results=results,
        facts_updated=eligibility.facts_updated if eligibility else [],
        sources=rag.sources if rag and rag.answer else [],
        turn_type=eligibility.turn_type if eligibility else "information",
        eligible=results[0].eligible if len(results) == 1 else None,
        missing_fields=results[0].missing if len(results) == 1 else [],
    )
