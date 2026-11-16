from typing import Literal

from pydantic import BaseModel

from eligibility_agent.agent import EligibilityOutput
from rag.agent import RagAnswer, RagSource
from supervisor.agent import SchemeResult


class SubTask(BaseModel):
    agent: Literal["eligibility", "rag"]
    text: str  # the part of the message this agent should handle
    scheme_id: str | None = None  # from the message, or the session's active scheme
    # eligibility only: True = asks whether the customer qualifies / what they
    # qualify for; False = just states a fact about themselves. None = let the
    # eligibility agent work it out itself.
    has_question: bool | None = None


class RoutePlan(BaseModel):
    subtasks: list[SubTask]  # 1..n, in the order they should run


class AgentOutput(BaseModel):
    """Opaque carrier for one agent's result; the orchestrator and refiner
    never look inside an agent, only at these fixed shapes."""

    agent: Literal["eligibility", "rag"]
    eligibility: EligibilityOutput | None = None
    rag: RagAnswer | None = None


class Refined(BaseModel):
    speech_text: str
    display_text: str


class SahayakResponse(BaseModel):
    reply_text: str  # spoken by the app
    display_text: str  # shown on screen
    language: str
    results: list[SchemeResult] = []
    facts_updated: list[str] = []
    sources: list[RagSource] = []
    turn_type: str
    # Conveniences for the app's existing (pre-RAG) fields.
    eligible: bool | None = None
    missing_fields: list[str] = []
