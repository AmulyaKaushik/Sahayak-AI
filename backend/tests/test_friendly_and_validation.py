"""Friendly wording, profile-value validation, rule-engine type safety and
the non-blocking eligibility agent."""

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from eligibility_agent import agent as eligibility_agent
from eligibility_engine.engine import check_eligibility
from main import app
from sahayak_ai import refiner
from sahayak_ai.models import AgentOutput
from schemas.profile_schema import InvalidProfileValue, get_profile_schema, validate_profile_value
from security.auth import create_access_token
from supervisor.agent import QueryResponse
from workers.friendly import friendly_text, requirement_label, scheme_name
from workers.narration_guard import fallback_narration, narration_contradicts_verdict

SPECS = {s.field: s for s in get_profile_schema()}


def test_fallback_narration_uses_friendly_names_and_no_raw_ids():
    text = fallback_narration(
        "retail_micro_loan", False, ["minimum_income"], ["employment_type_requirement", "dependents_cap"]
    )
    assert "_" not in text
    assert "Retail Micro Loan" in text
    assert "not eligible" in text
    assert "the employment type requirement and the limit on dependents" in text
    assert narration_contradicts_verdict(text, eligible=False) is False


def test_fallback_narration_eligible_wording():
    text = fallback_narration("home_loan", True, ["min_age"], [])
    assert text.startswith("You are eligible for Home Loan.")
    assert narration_contradicts_verdict(text, eligible=True) is False


def test_unknown_ids_are_still_readable():
    assert scheme_name("new_gold_loan") == "New Gold Loan"
    assert requirement_label("has_gold_receipt") == "has gold receipt"


def test_friendly_text_replaces_ids_inside_sentences():
    out = friendly_text("Not eligible for home_loan: has_property_papers missing, kisan_credit_card ok")
    assert "_" not in out and "Home Loan" in out and "Kisan Credit Card" in out


async def test_refiner_display_and_speech_have_no_raw_ids():
    out = AgentOutput(
        agent="eligibility",
        eligibility=eligibility_agent.EligibilityOutput(
            reply_text="Based on our records, you are not yet eligible for retail_micro_loan. "
            "Still needed: min_age."
        ),
    )
    refined = await refiner.refine([out], "en-IN")
    assert "_" not in refined.display_text and "_" not in refined.speech_text
    assert "Retail Micro Loan" in refined.display_text
    assert "Based on our records" not in refined.speech_text


async def test_pipeline_error_messages_are_friendly(monkeypatch):
    from types import SimpleNamespace

    import supervisor.agent as supervisor

    monkeypatch.setattr(
        supervisor,
        "_resolve_target",
        lambda **kw: SimpleNamespace(domain="loan", enumerate_all=False, target_scheme_id="nope"),
    )
    with pytest.raises(supervisor.PipelineError) as caught:
        await supervisor._resolve_target_scheme_ids("some loan", None)
    message = caught.value.message
    assert "_" not in message and "Retail Micro Loan" in message

    monkeypatch.setattr(
        supervisor,
        "_resolve_target",
        lambda **kw: SimpleNamespace(domain="unclear", enumerate_all=True, target_scheme_id=""),
    )
    with pytest.raises(supervisor.PipelineError) as caught:
        await supervisor._resolve_target_scheme_ids("hmm", None)
    assert "Could not" not in caught.value.message


# --- profile value validation ------------------------------------------------

@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("age", "35", 35),
        ("age", 35.0, 35),
        ("monthly_income", "25,000", 25000.0),
        ("has_girl_child_under_10", "yes", True),
        ("has_girl_child_under_10", False, False),
        ("employment_type", "farmer", "farmer"),
        ("land_holding_acres", 2.5, 2.5),
        ("age", None, None),
    ],
)
def test_valid_values_are_canonicalised(field, value, expected):
    assert validate_profile_value(SPECS[field], value) == expected


@pytest.mark.parametrize(
    "field,value",
    [
        ("age", "abc"),
        ("age", True),
        ("age", -3),
        ("age", 200),
        ("age", 35.5),
        ("monthly_income", float("nan")),
        ("land_holding_acres", "lots"),
        ("land_holding_acres", [1]),
        ("has_girl_child_under_10", "maybe"),
        ("employment_type", "astronaut"),
        ("existing_products", "jan_dhan_account"),
        ("existing_products", [1, 2]),
    ],
)
def test_invalid_values_are_rejected(field, value):
    with pytest.raises(InvalidProfileValue):
        validate_profile_value(SPECS[field], value)


def test_patch_profile_rejects_bad_types_with_422():
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token('cust-validation')}"}
    for body in ({"land_holding_acres": "lots"}, {"age": "abc"}, {"employment_type": "astronaut"}):
        response = client.patch("/api/v1/me/profile", json=body, headers=headers)
        assert response.status_code == 422, body


# --- rule engine never crashes on a wrongly-typed stored value ---------------

def test_engine_treats_wrongly_typed_value_as_unknown_not_crash():
    result = check_eligibility(
        "retail_micro_loan",
        {"age": "abc", "monthly_income": "lots", "dependents": [3], "employment_type": "salaried"},
    )
    assert result.eligible is False
    assert "min_age" in result.missing and "minimum_income" in result.missing


# --- the eligibility agent must not block the event loop ---------------------

async def test_eligibility_check_does_not_block_the_event_loop(monkeypatch):
    async def slow_pipeline(customer_id, session_id, text, scheme_id=None, has_question=None, facts_text=None):
        time.sleep(0.6)  # stands in for the blocking LLM / DB calls
        return QueryResponse(reply_text="ok", results=[], facts_updated=[], turn_type="acknowledgment")

    monkeypatch.setattr(eligibility_agent, "run_query_pipeline", slow_pipeline)

    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.05)
            ticks += 1

    task = asyncio.create_task(ticker())
    output = await eligibility_agent.check("c", "s", "hello")
    task.cancel()

    assert output.reply_text == "ok"
    assert ticks >= 8  # a blocked loop would have managed ~0
