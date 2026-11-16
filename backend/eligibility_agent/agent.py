"""Eligibility agent: the fixed interface Sahayak_AI uses for everything
about "am I eligible / here is a fact about me". A thin wrapper over the
existing supervisor pipeline -- behaviour is unchanged; this module only
fixes the input/output shape so the orchestrator never touches supervisor
internals."""

import asyncio

from pydantic import BaseModel

from supervisor.agent import (
    PipelineError,
    SchemeResult,
    get_active_scheme_id,
    run_query_pipeline,
)

__all__ = ["EligibilityOutput", "check", "active_scheme_id"]


class EligibilityOutput(BaseModel):
    results: list[SchemeResult] = []
    facts_updated: list[str] = []
    reply_text: str
    turn_type: str = "new_question"
    # Set instead of raising when the question can't be routed to a scheme,
    # so a voice user gets a spoken clarification rather than an HTTP error.
    needs_clarification: bool = False


async def check(
    customer_id: str,
    session_id: str,
    text: str,
    scheme_id: str | None = None,
    has_question: bool | None = None,
    facts_text: str | None = None,
) -> EligibilityOutput:
    try:
        # run_query_pipeline makes blocking LLM, Postgres and Redis calls. Run
        # it on its own thread (with its own event loop) so a slow turn never
        # freezes the server for every other customer.
        response = await asyncio.to_thread(
            asyncio.run,
            run_query_pipeline(
                customer_id, session_id, text, scheme_id=scheme_id, has_question=has_question,
                facts_text=facts_text,
            ),
        )
    except PipelineError as exc:
        return EligibilityOutput(
            reply_text=exc.message, turn_type="acknowledgment", needs_clarification=True
        )
    return EligibilityOutput(
        results=response.results,
        facts_updated=response.facts_updated,
        reply_text=response.reply_text,
        turn_type=response.turn_type,
    )


def active_scheme_id(session_id: str) -> str | None:
    return get_active_scheme_id(session_id)
