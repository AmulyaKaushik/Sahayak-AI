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

from typing import Literal

import dspy
from pydantic import BaseModel

from db_manager.repository import get_known_fields, get_profile, upsert_extra_facts
from eligibility_engine.engine import check_eligibility
from schemas.models import ContextEntry, CustomerProfile
from schemas.required_fields_seed import REQUIRED_FIELDS_ENTRIES, get_required_fields
from supervisor.context_store import SessionContextStore
from workers.base_worker import BaseWorkerAgent, build_lm
from workers.loan_agent.agent import LoanAgent
from workers.narration_guard import fallback_narration
from workers.scheme_agent.agent import SchemeAgent
from workers.signatures import ExtractFields

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


class QueryResponse(BaseModel):
    reply_text: str
    results: list[SchemeResult]
    facts_updated: list[str]
    turn_type: Literal["new_question", "recheck_unresolved", "acknowledgment"]


class ClassifyDomain(dspy.Signature):
    """Classify whether the customer's message is asking about a LOAN
    product (credit, borrowing money) or a government/bank SCHEME (a
    savings, subsidy, or welfare scheme). If the message is too ambiguous
    or off-topic to confidently tell which, answer "unclear" rather than
    guessing."""

    message: str = dspy.InputField()
    domain: Literal["loan", "scheme", "unclear"] = dspy.OutputField()


class ClassifyEnumerateMode(dspy.Signature):
    """Decide whether the customer is asking about ONE specific named
    loan/scheme, or ALL of them in this domain (e.g. "which all loans am I
    eligible for", "what schemes can I get", "which scheme am I eligible
    for" -- note this is enumerate_all=True too, even though it says
    "scheme" singular, because no specific scheme is named). Only set
    enumerate_all=False when a specific loan/scheme is clearly named or
    unambiguously implied in the message. If asking about one specific one,
    identify which scheme_id from available_scheme_ids it refers to. If you
    cannot confidently match it to exactly one of available_scheme_ids,
    default to enumerate_all=True rather than guessing a specific one."""

    message: str = dspy.InputField()
    domain: str = dspy.InputField(desc="'loan' or 'scheme'.")
    available_scheme_ids: list[str] = dspy.InputField()
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
_classify_domain = dspy.Predict(ClassifyDomain)
_classify_enumerate = dspy.Predict(ClassifyEnumerateMode)
_classify_turn_intent = dspy.Predict(ClassifyTurnIntent)

_context_store = SessionContextStore()


def _default_profile(customer_id: str) -> CustomerProfile:
    return CustomerProfile(
        customer_id=customer_id,
        monthly_income=None,
        age=None,
        dependents=None,
        employment_type=None,
        existing_products=[],
        language_preference=None,
    )


def _worker_for_scheme(scheme_id: str) -> BaseWorkerAgent:
    if scheme_id in LoanAgent.domain_scheme_ids:
        return LoanAgent()
    if scheme_id in SchemeAgent.domain_scheme_ids:
        return SchemeAgent()
    raise PipelineError("unknown_scheme", f"No worker handles scheme_id={scheme_id!r}")


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


async def _check_schemes(
    text: str, profile: CustomerProfile, scheme_ids: list[str], known_fields_base: dict
) -> tuple[list[SchemeResult], list[str], list[str]]:
    """Runs handle_query + the authoritative recompute for each scheme_id.
    Returns (results, reply_sentences, workers_called_this_turn)."""
    results: list[SchemeResult] = []
    reply_sentences: list[str] = []
    workers_called: list[str] = []

    for scheme_id in scheme_ids:
        worker = _worker_for_scheme(scheme_id)
        required_fields = get_required_fields(scheme_id)
        workers_called.append(scheme_id)

        worker_result = await worker.handle_query(text, profile, scheme_id, required_fields)

        # handle_query's own internal engine call never sees session/
        # persisted/request-level facts (its signature is frozen -- see
        # workers/base_worker.py). Recompute authoritatively here with
        # everything merged, deterministically.
        known_fields = {**known_fields_base, **worker_result.extracted_fields}
        authoritative = check_eligibility(scheme_id, known_fields)

        results.append(
            SchemeResult(
                scheme_id=scheme_id,
                eligible=authoritative.eligible,
                satisfied=authoritative.satisfied,
                missing=authoritative.missing,
            )
        )
        sentence = fallback_narration(
            scheme_id, authoritative.eligible, authoritative.satisfied, authoritative.missing
        )
        if not authoritative.eligible:
            sentence += _missing_field_prompt(scheme_id, known_fields)
        reply_sentences.append(sentence)

    return results, reply_sentences, workers_called


async def run_query_pipeline(
    customer_id: str, session_id: str, text: str, extra_fields: dict | None = None
) -> QueryResponse:
    extra_fields = extra_fields or {}
    profile = get_profile(customer_id) or _default_profile(customer_id)

    past_entries = _context_store.read(session_id)
    session_known_fields = _merge_session_known_fields(past_entries)
    persisted_extra_facts = get_known_fields(customer_id)  # profile + cross-session extra facts

    baseline_known_fields = {
        **persisted_extra_facts,
        **session_known_fields,
        **extra_fields,
    }

    lm = build_lm()

    # (a) Fact extraction first, unconditionally, against every scheme's
    # required fields combined -- not just one "in-focus" scheme.
    with dspy.context(lm=lm):
        extraction = _extract_all_fields(
            message=text, required_fields=ALL_REQUIRED_FIELDS, known_fields=baseline_known_fields
        )
    newly_extracted = extraction.extracted_fields

    # (b) Persist genuinely new/changed facts; merge into this turn's set.
    facts_written = upsert_extra_facts(customer_id, newly_extracted, source="conversation")
    known_fields = {**baseline_known_fields, **newly_extracted}

    # (d) Classify what this turn is asking for.
    with dspy.context(lm=lm):
        has_question = _classify_turn_intent(message=text).has_question

    results: list[SchemeResult] = []
    reply_sentences: list[str] = []
    workers_called_this_turn: list[str] = []
    turn_type: Literal["new_question", "recheck_unresolved", "acknowledgment"]

    if has_question:
        turn_type = "new_question"

        with dspy.context(lm=lm):
            domain = _classify_domain(message=text).domain

        if domain not in ("loan", "scheme"):
            raise PipelineError(
                "domain_unclear",
                "Could not confidently tell whether this question is about a loan or a scheme. "
                "Try mentioning 'loan' or the name of a specific scheme.",
            )

        domain_worker = LoanAgent() if domain == "loan" else SchemeAgent()

        with dspy.context(lm=lm):
            enumerate_prediction = _classify_enumerate(
                message=text, domain=domain, available_scheme_ids=domain_worker.domain_scheme_ids
            )

        if enumerate_prediction.enumerate_all:
            target_scheme_ids = list(domain_worker.domain_scheme_ids)
        else:
            target_scheme_id = enumerate_prediction.target_scheme_id
            if target_scheme_id not in domain_worker.domain_scheme_ids:
                raise PipelineError(
                    "scheme_unresolved",
                    f"Could not confidently match this question to a specific {domain} we cover. "
                    f"Available options: {', '.join(domain_worker.domain_scheme_ids)}.",
                )
            target_scheme_ids = [target_scheme_id]

        results, reply_sentences, workers_called_this_turn = await _check_schemes(
            text, profile, target_scheme_ids, known_fields
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
            results, reply_sentences, workers_called_this_turn = await _check_schemes(
                text, profile, awaiting_before, known_fields
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

    _context_store.write(
        ContextEntry(
            session_id=session_id,
            turn_index=len(past_entries),
            summary=f"{turn_type}: {', '.join(workers_called_this_turn) or 'no scheme checked'}.",
            fields_collected_this_session=fields_collected_this_session,
            workers_called=prior_workers_called + workers_called_this_turn,
            written_by="supervisor",
        )
    )

    return QueryResponse(
        reply_text=" ".join(reply_sentences),
        results=results,
        facts_updated=list(facts_written.keys()),
        turn_type=turn_type,
    )
