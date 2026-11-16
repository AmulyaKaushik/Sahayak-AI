"""Session-aware query pipeline: sentence in -> unconditional fact
extraction -> turn-intent classification -> worker(s) -> merged structured
answer out.

run_query_pipeline() is the single shared entry point: both the
/api/v1/query route (supervisor/query_api.py) and the dev CLI
(scripts/cli.py) call it directly, so there is exactly one implementation
of this logic, not two that could drift apart.

Every turn, unconditionally, in this order:
  (a) Extract facts from the message against the UNION of every scheme's
      required fields (not just one "in-focus" scheme) -- see
      ALL_REQUIRED_FIELDS below.
  (b) Persist genuinely new/changed facts per-customer via
      db_manager.repository.upsert_extra_facts (the EAV-style
      customer_profile_field_history table -- see that module's docstring),
      so a fact given today is still known in a future session, not just
      this one. Also merge into this turn's working known_fields.
  (c) Persisted extra facts are loaded at the start of every turn (not just
      session start) and merged in before any eligibility check runs --
      this is what makes facts survive across sessions.
  (d) THEN classify what this turn is asking for -- exactly one of:
        - a new single-scheme/loan question
        - a new enumerate question ("which all X am I eligible for")
        - no question at all, just a fact -- re-check whichever scheme_ids
          were discussed this session and are STILL not-eligible-due-to-
          missing-fields (recomputed fresh from current facts, never from
          stale stored state), or acknowledge if nothing's pending.

This replaces the prior single-scheme "in-focus, does this look like an
answer" mechanism entirely -- it couldn't handle multiple in-focus schemes
or a turn that both states a fact and asks a new question, and it was too
reliant on domain classification succeeding for a message that might have
no loan/scheme signal at all (a pure fact statement never needs domain
classification now, since it's detected via turn-intent, not routed).

Section 2 constraint #3 (single writer) still holds: this module owns the
one SessionContextStore instance and is the only thing that calls .write()
on it. handle_query's signature/internals are untouched -- it never
receives a reference to any store.
"""

import asyncio
import logging
from typing import Literal

import dspy
from pydantic import BaseModel

from db_manager.repository import get_known_fields, upsert_extra_facts
from eligibility_engine.engine import check_eligibility
from schemas.models import ContextEntry
from schemas.required_fields_seed import REQUIRED_FIELDS_ENTRIES, get_required_fields
from supervisor.context_store import SessionContextStore
from workers.base_worker import build_fast_lm, build_lm
from workers.friendly import join_natural, scheme_name
from workers.loan_agent.agent import LoanAgent
from workers.narration_guard import fallback_narration
from workers.scheme_agent.agent import SchemeAgent
from supervisor.offline import extract_facts_regex, keyword_target_scheme_ids
from workers.signatures import ExtractFields

logger = logging.getLogger(__name__)

ALL_REQUIRED_FIELDS: list[str] = sorted(
    {field for entry in REQUIRED_FIELDS_ENTRIES for field in entry.required_fields}
)


class PipelineError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class SchemeResult(BaseModel):
    scheme_id: str
    eligible: bool
    satisfied: list[str]
    missing: list[str]
    # Fields the customer still has to give for this scheme (for the reply to ask).
    ask: list[str] = []


class QueryResponse(BaseModel):
    reply_text: str
    results: list[SchemeResult]
    facts_updated: list[str]
    turn_type: Literal["new_question", "recheck_unresolved", "acknowledgment"]


class ResolveTarget(dspy.Signature):
    """Work out which loan(s) or scheme(s) the customer is asking about.

    domain: "loan" (credit, borrowing money), "scheme" (a savings, subsidy
    or welfare scheme) or "both" (ONLY when the customer says both words, loans AND schemes,
    e.g. "which loans and schemes am I eligible for"; vague words like
    "products" or "options" stay "unclear"). If the message is too ambiguous or off-topic to tell
    which, answer "unclear" rather than guessing.

    enumerate_all: True when the customer asks about ALL of them in that
    domain ("which all loans am I eligible for", "what schemes can I get",
    "which scheme am I eligible for" -- True even though "scheme" is
    singular, because none is named). False only when ONE specific
    loan/scheme is clearly named or unambiguously implied. If False, give
    target_scheme_id from the ids listed for that domain; if you cannot
    confidently match exactly one, use enumerate_all=True instead of
    guessing. A fact the customer mentions about themselves (a child, an
    income, land) is NOT the name of a scheme: only a loan/scheme actually
    named, or referred to as "this one", makes enumerate_all False."""

    message: str = dspy.InputField()
    loan_scheme_ids: list[str] = dspy.InputField()
    scheme_scheme_ids: list[str] = dspy.InputField(desc="Ids of the government/bank schemes.")
    domain: Literal["loan", "scheme", "both", "unclear"] = dspy.OutputField()
    enumerate_all: bool = dspy.OutputField()
    target_scheme_id: str = dspy.OutputField(
        desc="Empty string if enumerate_all is True, or if no confident single match exists."
    )


class ClassifyTurnIntent(dspy.Signature):
    """Decide whether the customer's message contains a QUESTION asking to
    check eligibility for a loan or scheme (has_question=True), or is
    purely stating information with no such question in it
    (has_question=False). A message can both state a new fact AND ask a
    question in the same sentence (e.g. "I have a child who is 8, so now
    tell me which scheme am I eligible for") -- if there's a question
    anywhere in it, has_question is True."""

    message: str = dspy.InputField()
    has_question: bool = dspy.OutputField()


_extract_all_fields = dspy.Predict(ExtractFields)
_resolve_target = dspy.Predict(ResolveTarget)
_classify_turn_intent = dspy.Predict(ClassifyTurnIntent)

_context_store = SessionContextStore()


def _is_known(value) -> bool:
    return value is not None and value != []


def _outstanding_fields(scheme_id: str, known_fields: dict) -> list[str]:
    return [f for f in get_required_fields(scheme_id) if not _is_known(known_fields.get(f))]


# Hand-authored, same spirit as rules_seed.py/required_fields_seed.py: the
# engine's "missing" list only ever reports requirement ids (internal
# labels like "has_land_holding"), which told the customer THAT something
# was missing but not WHAT specifically to say. A customer answering "I do
# have land holding" (no number) satisfies nothing, because land_holding_
# acres needs an actual quantity and the extractor correctly won't invent
# one -- the fix is telling them that plainly, not guessing a number.
FIELD_PROMPTS: dict[str, str] = {
    "has_girl_child_under_10": "whether you have a girl child under 10 years old",
    "owns_pucca_house": "whether you already own a pucca (permanent) house",
    "is_first_time_home_buyer": "whether this would be your first home purchase",
    "land_holding_acres": "how many acres of land you own",
    "age": "your age",
    "monthly_income": "your monthly income",
    "employment_type": "your employment type (salaried, self-employed, farmer, or government employee)",
    "dependents": "how many dependents you have",
    "existing_products": "which bank products or accounts you already have",
    "has_business_plan": "whether you have a business plan for your enterprise",
    "has_property_papers": "whether you have the property papers ready for the home you want to buy",
}


def _missing_field_prompt(scheme_id: str, known_fields: dict) -> str:
    outstanding = _outstanding_fields(scheme_id, known_fields)
    if not outstanding:
        return ""
    prompts = [FIELD_PROMPTS.get(field, field) for field in outstanding]
    return " To check this, please tell me " + " and ".join(prompts) + "."


def _real_collected_fields(fields_collected: dict) -> dict:
    return {k: v for k, v in fields_collected.items() if not k.startswith("__")}


def _merge_session_known_fields(entries: list[ContextEntry]) -> dict:
    merged: dict = {}
    for entry in entries:
        merged.update(_real_collected_fields(entry.fields_collected_this_session))
    return merged


def _discussed_scheme_ids(entries: list[ContextEntry]) -> list[str]:
    seen: list[str] = []
    for entry in entries:
        for scheme_id in entry.workers_called:
            if scheme_id not in seen:
                seen.append(scheme_id)
    return seen


def _check_schemes(
    scheme_ids: list[str], known_fields: dict
) -> tuple[list[SchemeResult], list[str], list[str]]:
    """Deterministic engine check per scheme_id. No LLM: the worker agents'
    extra extraction and narration used to run here too, but their output was
    discarded (facts were already extracted for every scheme this turn, and
    the reply is built from the engine result). Returns (results,
    reply_sentences, workers_called_this_turn)."""
    results: list[SchemeResult] = []
    reply_sentences: list[str] = []

    for scheme_id in scheme_ids:
        if not _is_known_scheme(scheme_id):
            raise PipelineError("unknown_scheme", f"No worker handles scheme_id={scheme_id!r}")
        authoritative = check_eligibility(scheme_id, known_fields)

        results.append(
            SchemeResult(
                scheme_id=scheme_id,
                eligible=authoritative.eligible,
                satisfied=authoritative.satisfied,
                missing=authoritative.missing,
                ask=[] if authoritative.eligible else _outstanding_fields(scheme_id, known_fields),
            )
        )
        sentence = fallback_narration(
            scheme_id, authoritative.eligible, authoritative.satisfied, authoritative.missing
        )
        if not authoritative.eligible:
            sentence += _missing_field_prompt(scheme_id, known_fields)
        reply_sentences.append(sentence)

    return results, reply_sentences, list(scheme_ids)


def _is_known_scheme(scheme_id: str) -> bool:
    return scheme_id in LoanAgent.domain_scheme_ids or scheme_id in SchemeAgent.domain_scheme_ids


def _resolve_sync(text: str, lm):
    with dspy.context(lm=lm):
        return _resolve_target(
            message=text,
            loan_scheme_ids=LoanAgent.domain_scheme_ids,
            scheme_scheme_ids=SchemeAgent.domain_scheme_ids,
        )


async def _resolve_target_scheme_ids(text: str, lm, active_scheme_id: str | None = None) -> list[str]:
    try:
        prediction = await asyncio.to_thread(_resolve_sync, text, lm)
    except Exception:
        # LLM unreachable (offline, rate limit): work it out from the words.
        logger.warning("Supervisor: target LLM failed; using keywords", exc_info=True)
        guess = keyword_target_scheme_ids(
            text, LoanAgent.domain_scheme_ids, SchemeAgent.domain_scheme_ids, active_scheme_id
        )
        if guess:
            return guess
        raise PipelineError(
            "domain_unclear",
            "I'm having trouble understanding that right now. Please say the name of the "
            "loan or scheme you want me to check.",
        )
    domain = prediction.domain

    if domain == "both":
        return list(LoanAgent.domain_scheme_ids) + list(SchemeAgent.domain_scheme_ids)

    if domain not in ("loan", "scheme"):
        raise PipelineError(
            "domain_unclear",
            "I'm not sure whether you are asking about a loan or a scheme. "
            "Please say the name of the loan or scheme you want me to check.",
        )

    domain_ids = LoanAgent.domain_scheme_ids if domain == "loan" else SchemeAgent.domain_scheme_ids

    if prediction.enumerate_all:
        return list(domain_ids)

    target_scheme_id = prediction.target_scheme_id
    if target_scheme_id not in domain_ids:
        raise PipelineError(
            "scheme_unresolved",
            f"I could not tell which {domain} you mean. I can check: "
            f"{join_natural([scheme_name(s) for s in domain_ids])}.",
        )
    return [target_scheme_id]


def _extract_sync(text: str, known_fields: dict, lm) -> dict:
    with dspy.context(lm=lm):
        return _extract_all_fields(
            message=text, required_fields=ALL_REQUIRED_FIELDS, known_fields=known_fields
        ).extracted_fields


def _intent_sync(text: str, lm) -> bool:
    with dspy.context(lm=lm):
        return _classify_turn_intent(message=text).has_question


def get_active_scheme_id(session_id: str) -> str | None:
    """The scheme/loan this session is currently about (None if unknown)."""
    entries = _context_store.read(session_id)
    return entries[-1].active_scheme_id if entries else None


async def run_query_pipeline(
    customer_id: str,
    session_id: str,
    text: str,
    extra_fields: dict | None = None,
    scheme_id: str | None = None,
    has_question: bool | None = None,
    facts_text: str | None = None,
) -> QueryResponse:
    """scheme_id, when given and known, pins the question to that scheme and
    skips domain/enumerate classification (the caller has already resolved
    it, e.g. from "this loan" + the session's active scheme).

    has_question, when given (Sahayak_AI's router decides it), replaces the
    separate "is this a question or a fact" LLM call.

    The independent LLM calls of a turn (fact extraction, and target or
    intent classification when needed) run at the same time.

    facts_text, when given, is the customer's full original message: facts are
    extracted from it, while `text` (the router's cleaned-up question) is used
    for classification. Without it a rewritten question would lose the facts."""
    extra_fields = extra_fields or {}

    past_entries = _context_store.read(session_id)
    session_known_fields = _merge_session_known_fields(past_entries)
    persisted_extra_facts = get_known_fields(customer_id)  # profile + cross-session extra facts

    baseline_known_fields = {
        **persisted_extra_facts,
        **session_known_fields,
        **extra_fields,
    }

    smart_lm, fast_lm = build_lm(), build_fast_lm()
    prior_active = past_entries[-1].active_scheme_id if past_entries else None
    pinned = bool(scheme_id and _is_known_scheme(scheme_id))

    # (a) Fact extraction, unconditionally, against every scheme's required
    # fields combined -- not just one "in-focus" scheme. Runs alongside the
    # classification it doesn't depend on.
    parallel = {"extract": asyncio.to_thread(_extract_sync, facts_text or text, baseline_known_fields, smart_lm)}
    if has_question is None:
        parallel["intent"] = asyncio.to_thread(_intent_sync, text, fast_lm)
    elif has_question and not pinned:
        parallel["target"] = _resolve_target_scheme_ids(text, smart_lm, prior_active)
    outcome = dict(zip(parallel, await asyncio.gather(*parallel.values(), return_exceptions=True)))

    # Regex facts are the safety net: they fill what the LLM missed ("I am a
    # farmer") and are used alone when the LLM can't be reached. The LLM wins
    # when both give the same field.
    regex_facts = extract_facts_regex(facts_text or text)
    if isinstance(outcome["extract"], BaseException):
        logger.warning("Supervisor: extraction LLM failed; using regex facts", exc_info=outcome["extract"])
        newly_extracted = regex_facts
    else:
        newly_extracted = {**regex_facts, **outcome["extract"]}

    # (b) Persist genuinely new/changed facts; merge into this turn's set.
    # Done before surfacing a classification error, so a fact the customer
    # stated is kept even when their question can't be routed.
    facts_written = upsert_extra_facts(customer_id, newly_extracted, source="conversation")
    known_fields = {**baseline_known_fields, **newly_extracted}

    # (d) What is this turn asking for?
    if has_question is None:
        if isinstance(outcome["intent"], BaseException):
            raise outcome["intent"]
        has_question = outcome["intent"]

    results: list[SchemeResult] = []
    reply_sentences: list[str] = []
    workers_called_this_turn: list[str] = []
    turn_type: Literal["new_question", "recheck_unresolved", "acknowledgment"]

    if has_question:
        turn_type = "new_question"

        if pinned:
            target_scheme_ids = [scheme_id]
        else:
            target = outcome["target"] if "target" in outcome else None
            if target is None:  # the "is it a question" call ran first; resolve now
                target = await _resolve_target_scheme_ids(text, smart_lm, prior_active)
            if isinstance(target, BaseException):
                raise target
            target_scheme_ids = target

        results, reply_sentences, workers_called_this_turn = _check_schemes(
            target_scheme_ids, known_fields
        )
    else:
        # No question in this turn -- re-check whatever discussed schemes
        # were awaiting info BEFORE this turn's fact (using baseline_known_
        # fields, i.e. facts known prior to this turn), then report their
        # CURRENT status with the new fact applied -- including the case
        # where it just resolved them to eligible. Filtering on "still
        # unresolved" AFTER merging the new fact would silently drop exactly
        # the schemes this fact was meant to resolve.
        awaiting_before = [
            scheme_id
            for scheme_id in _discussed_scheme_ids(past_entries)
            if not check_eligibility(scheme_id, baseline_known_fields).eligible
            and _outstanding_fields(scheme_id, baseline_known_fields)
        ]

        if awaiting_before:
            turn_type = "recheck_unresolved"
            results, reply_sentences, workers_called_this_turn = _check_schemes(
                awaiting_before, known_fields
            )
        else:
            turn_type = "acknowledgment"
            reply_sentences = (
                ["Got it, I've noted that."]
                if facts_written
                else ["I didn't catch a specific question -- what would you like checked?"]
            )

    fields_collected_this_session = {**session_known_fields, **newly_extracted}
    prior_workers_called = past_entries[-1].workers_called if past_entries else []
    prior_active_scheme_id = past_entries[-1].active_scheme_id if past_entries else None
    active_scheme_id = (
        workers_called_this_turn[0] if len(workers_called_this_turn) == 1 else prior_active_scheme_id
    )

    _context_store.write(
        ContextEntry(
            session_id=session_id,
            turn_index=len(past_entries),
            summary=f"{turn_type}: {', '.join(workers_called_this_turn) or 'no scheme checked'}.",
            fields_collected_this_session=fields_collected_this_session,
            workers_called=prior_workers_called + workers_called_this_turn,
            written_by="supervisor",
            active_scheme_id=active_scheme_id,
        )
    )

    return QueryResponse(
        reply_text=" ".join(reply_sentences),
        results=results,
        facts_updated=list(facts_written.keys()),
        turn_type=turn_type,
    )
