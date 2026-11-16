"""Router: one DSPy call turns a message into an ordered list of sub-tasks,
so a single sentence can be handled by more than one agent. It never raises
at a voice user -- on any failure it falls back to a heuristic plan."""

import asyncio
import logging
import re

import dspy

from sahayak_ai.models import RoutePlan, SubTask
from schemas.required_fields_seed import REQUIRED_FIELDS_ENTRIES
from workers.base_worker import build_fast_lm

logger = logging.getLogger(__name__)

KNOWN_SCHEME_IDS: list[str] = [e.scheme_or_loan_id for e in REQUIRED_FIELDS_ENTRIES]


class RouteMessage(dspy.Signature):
    """Split the customer's message into an ordered list of sub-tasks, each
    handled by exactly one agent:
      - "eligibility": checking whether the customer qualifies for a loan or
        scheme, OR the customer stating a fact about themselves (age, income,
        children, land, ...) with no question. The agent extracts and stores
        the fact and re-checks.
      - "rag": a question about what a loan/scheme's official document says
        (conditions, ages, limits, documents needed, benefits, reasons).
    One sentence may need both: emit one sub-task per agent, each with only
    its own part of the message in `text`. Every `text` must be a complete,
    standalone question that names its subject (the loan/scheme, the fact
    asked about), because the agent sees nothing else: never leave a
    fragment like "why only till then?". Resolve "this loan"/"this scheme"
    using active_scheme_id; set scheme_id only to a value from
    available_scheme_ids, else leave it empty. Leave scheme_id empty when
    the customer asks about ALL loans/schemes ("which loans am I eligible
    for"), even if one is active. For an "eligibility" sub-task set
    has_question=True when the customer asks whether they qualify or what they
    qualify for, and has_question=False when they only state a fact about
    themselves. A question about what the
    official document says (an age limit, amount, duration, documents
    needed) is a "rag" sub-task even when it mentions the customer's
    situation; use "eligibility" only when the customer asks whether THEY
    qualify or states a fact about themselves.

    Examples:
    "Am I eligible for the PM loan?" -> [eligibility("Am I eligible for the PM loan?")]
    "What is the minimum age of the daughter?" -> [rag("What is the minimum age of the daughter?")]
    "I have a daughter who is 17" -> [eligibility("I have a daughter who is 17")]
    "What is the minimum age for this loan and why" -> [rag("What is the minimum age for this loan?"), rag("Why is there a minimum age for this loan?")]
    "Am I eligible for the home loan and what documents do I need?" -> [eligibility("Am I eligible for the home loan?"), rag("What documents are needed for the home loan?")]
    "Which loans am I eligible for?" -> [eligibility("Which loans am I eligible for?")] with scheme_id empty
    """

    message: str = dspy.InputField()
    active_scheme_id: str = dspy.InputField(desc="Scheme the conversation is about, or empty.")
    available_scheme_ids: list[str] = dspy.InputField()
    subtasks: list[SubTask] = dspy.OutputField(desc="Ordered sub-tasks, at least one.")


_route = dspy.Predict(RouteMessage)

_ELIGIBILITY_HINT = re.compile(
    r"\b(eligib\w*|qualif\w*|can i (get|apply|open|take)|am i able|do i get)\b", re.I
)
_ALL_OF_THEM = re.compile(r"\b(which|what|all|any)\b.*\b(loans?|schemes?)\b", re.I)
_QUESTION_START = re.compile(
    r"^\s*(what|why|how|when|where|which|who|is|are|does|do|can|tell me|explain)\b", re.I
)


def fallback_plan(text: str, active_scheme_id: str | None) -> RoutePlan:
    """Questions about eligibility -> eligibility; other questions -> rag;
    statements -> eligibility (they are facts to store)."""
    is_question = "?" in text or bool(_QUESTION_START.match(text))
    if _ELIGIBILITY_HINT.search(text) or not is_question:
        agent = "eligibility"
    else:
        agent = "rag"
    scheme_id = None if _ALL_OF_THEM.search(text) else active_scheme_id
    has_question = is_question or bool(_ELIGIBILITY_HINT.search(text))
    return RoutePlan(
        subtasks=[
            SubTask(
                agent=agent,
                text=text,
                scheme_id=scheme_id,
                has_question=has_question if agent == "eligibility" else None,
            )
        ]
    )


def _clean(plan_subtasks: list, text: str, active_scheme_id: str | None) -> RoutePlan:
    cleaned: list[SubTask] = []
    for item in plan_subtasks:
        try:
            subtask = item if isinstance(item, SubTask) else SubTask.model_validate(item)
        except Exception:
            continue
        if not subtask.text.strip():
            subtask = subtask.model_copy(update={"text": text})
        # The model resolves "this loan" from active_scheme_id itself. Falling
        # back to the active scheme here would also pin "which loans am I
        # eligible for" to whatever was discussed last, so an unknown or
        # empty id stays empty.
        scheme_id = subtask.scheme_id if subtask.scheme_id in KNOWN_SCHEME_IDS else None
        cleaned.append(subtask.model_copy(update={"scheme_id": scheme_id}))
    return RoutePlan(subtasks=cleaned[:3])


def _route_sync(text: str, active_scheme_id: str | None) -> RoutePlan:
    with dspy.context(lm=build_fast_lm()):
        prediction = _route(
            message=text,
            active_scheme_id=active_scheme_id or "",
            available_scheme_ids=KNOWN_SCHEME_IDS,
        )
    plan = _clean(list(prediction.subtasks), text, active_scheme_id)
    return plan if plan.subtasks else fallback_plan(text, active_scheme_id)


async def route(text: str, active_scheme_id: str | None = None) -> RoutePlan:
    try:
        return await asyncio.to_thread(_route_sync, text, active_scheme_id)
    except Exception:
        logger.warning("Router: LLM routing failed; using the keyword fallback", exc_info=True)
        return fallback_plan(text, active_scheme_id)
