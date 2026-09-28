"""Phase 4 test: the worker's stated eligibility always matches the engine's
eligible field exactly (automated check comparing narration claims against
the structured result), for both worker agents and across a genuinely
eligible and a genuinely ineligible case."""

import pytest

from eligibility_engine.engine import check_eligibility
from eligibility_engine.rules_repository import get_required_field_names
from schemas.models import CustomerProfile
from workers.loan_agent.agent import LoanAgent
from workers.narration_guard import narration_contradicts_verdict
from workers.scheme_agent.agent import SchemeAgent


async def _run_and_check(worker, message, profile, scheme_id):
    required_fields = get_required_field_names(scheme_id)
    result = await worker.handle_query(message, profile, scheme_id, required_fields)

    engine_result = check_eligibility(scheme_id, {**profile.model_dump(), **result.extracted_fields})

    # The structural invariant: eligible is always copied verbatim from the
    # engine, so this holds by construction -- but we assert it anyway as a
    # regression guard.
    assert result.eligible == engine_result.eligible

    # The narration-matches-engine check: the LLM's prose must not claim the
    # opposite verdict from what the engine decided.
    assert narration_contradicts_verdict(result.narration, result.eligible) is False

    return result


@pytest.mark.asyncio
async def test_scheme_agent_eligible_case():
    profile = CustomerProfile(
        customer_id="cust-worker-1",
        monthly_income=None,
        age=65,
        dependents=None,
        employment_type=None,
        existing_products=[],
        language_preference="hi",
    )
    result = await _run_and_check(
        SchemeAgent(),
        "I am 65 years old, do I qualify for the senior citizen savings scheme?",
        profile,
        "senior_citizen_savings_scheme",
    )
    assert result.eligible is True
    assert result.missing == []


@pytest.mark.asyncio
async def test_scheme_agent_not_eligible_case():
    profile = CustomerProfile(
        customer_id="cust-worker-2",
        monthly_income=None,
        age=40,
        dependents=None,
        employment_type=None,
        existing_products=[],
        language_preference="hi",
    )
    result = await _run_and_check(
        SchemeAgent(),
        "I'm 40 years old, can I open a senior citizen savings account?",
        profile,
        "senior_citizen_savings_scheme",
    )
    assert result.eligible is False
    assert result.missing == ["minimum_age_60"]


@pytest.mark.asyncio
async def test_loan_agent_extracts_field_from_message():
    profile = CustomerProfile(
        customer_id="cust-worker-3",
        monthly_income=None,
        age=30,
        dependents=2,
        employment_type=None,
        existing_products=[],
        language_preference="en",
    )
    result = await _run_and_check(
        LoanAgent(),
        "I'm a salaried employee earning 20000 rupees a month, can I get a personal loan?",
        profile,
        "retail_micro_loan",
    )
    assert result.extracted_fields.get("employment_type") == "salaried"
    assert result.eligible is True


@pytest.mark.asyncio
async def test_worker_rejects_scheme_outside_its_domain():
    profile = CustomerProfile(
        customer_id="cust-worker-4",
        monthly_income=None,
        age=30,
        dependents=None,
        employment_type=None,
        existing_products=[],
        language_preference=None,
    )
    with pytest.raises(ValueError):
        await LoanAgent().handle_query("hi", profile, "senior_citizen_savings_scheme", [])
