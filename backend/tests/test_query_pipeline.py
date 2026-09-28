"""Tests for the /api/v1/query pipeline (supervisor/agent.py), hit through
the actual running FastAPI app -- not just the pipeline function directly --
so these also prove the router is really wired into main.py.

The five regression tests at the bottom reproduce the two real conversation
failures that motivated replacing the old single-scheme "in-focus
continuation" mechanism with unconditional fact extraction + three-way turn
classification (new_question / recheck_unresolved / acknowledgment)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from main import app
from workers.loan_agent.agent import LoanAgent
from workers.scheme_agent.agent import SchemeAgent

client = TestClient(app)


def _sid() -> str:
    return str(uuid.uuid4())


def _cid(label: str) -> str:
    # Facts extracted from any query now persist per-customer in Postgres
    # (that's the whole point of this task) -- so customer_id must be
    # unique per test run too, not just session_id, or reruns leak state
    # from the previous run.
    return f"cust-{label}-{uuid.uuid4()}"


def _query(customer_id: str, session_id: str, text: str, extra_fields: dict | None = None):
    body = {"customer_id": customer_id, "session_id": session_id, "text": text}
    if extra_fields is not None:
        body["extra_fields"] = extra_fields
    return client.post("/api/v1/query", json=body)


def test_single_scheme_query_returns_one_result():
    response = _query(
        _cid("query-1"), _sid(), "I am 65 years old, can I open a senior citizen savings account?"
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 1
    assert body["results"][0]["scheme_id"] == "senior_citizen_savings_scheme"
    assert body["results"][0]["eligible"] is True
    assert body["reply_text"]
    assert body["turn_type"] == "new_question"


def test_enumerate_query_covers_every_loan_scheme_id():
    response = _query(_cid("query-2"), _sid(), "which all loans am I eligible for")
    assert response.status_code == 200
    body = response.json()
    returned_scheme_ids = {r["scheme_id"] for r in body["results"]}
    assert returned_scheme_ids == set(LoanAgent.domain_scheme_ids)


def test_unknown_customer_id_returns_valid_response_not_error():
    response = _query(
        _cid("query-does-not-exist-anywhere"), _sid(), "Can I open a Jan Dhan savings account?"
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 1
    # age is unknown for a nonexistent customer -> minimum_age can't be confirmed
    assert "minimum_age" in body["results"][0]["missing"]


def test_ambiguous_eligibility_question_returns_structured_error():
    # A message that clearly asks a question but gives no loan/scheme signal
    # to route on. A purely off-topic message (e.g. "tell me a joke") is no
    # longer an error case under the new design -- it's correctly recognized
    # as not an eligibility question at all and gets an acknowledgment
    # instead (see test_off_topic_message_gets_acknowledgment_not_error).
    response = _query(_cid("query-4"), _sid(), "Am I eligible for any of your financial products?")
    assert response.status_code == 422
    body = response.json()
    assert "error" in body
    assert "code" in body["error"]
    assert "message" in body["error"]


def test_off_topic_message_gets_acknowledgment_not_error():
    response = _query(_cid("query-4b"), _sid(), "Tell me a joke about cats.")
    assert response.status_code == 200
    body = response.json()
    assert body["turn_type"] == "acknowledgment"
    assert body["results"] == []


def test_extra_fields_changes_eligibility_result():
    text = "Can I open a Sukanya Samriddhi account? I am 30."

    without = _query(_cid("query-5"), _sid(), text).json()
    with_extra = _query(
        _cid("query-5b"), _sid(), text, extra_fields={"has_girl_child_under_10": True}
    ).json()

    assert without["results"][0]["eligible"] is False
    assert with_extra["results"][0]["eligible"] is True


# --- Regression tests for the two reproduced conversation failures --------


def test_a_combined_fact_and_enumerate_question_succeeds_and_applies_the_fact():
    """Failure 1: enumerate schemes, several come back with different missing
    fields, then a single follow-up both states a new fact AND asks a new
    enumerate question. Must succeed (no error) and re-evaluate every
    scheme_id with the new fact applied."""
    session_id = _sid()
    customer_id = _cid("regress-a")

    first = _query(customer_id, session_id, "which all schemes am I eligible for").json()
    assert len(first["results"]) == len(SchemeAgent.domain_scheme_ids)

    second = _query(
        customer_id,
        session_id,
        "I have a child who is 8 years old so now tell me which scheme am I eligible for",
    )
    assert second.status_code == 200
    body = second.json()
    returned_scheme_ids = {r["scheme_id"] for r in body["results"]}
    assert returned_scheme_ids == set(SchemeAgent.domain_scheme_ids)


def test_missing_field_reply_asks_for_the_specific_quantity_needed():
    """A NOT ELIGIBLE reply for a numeric missing field (land_holding_acres)
    must tell the customer what specific information to give -- not just
    the opaque internal requirement id (has_land_holding) -- since a vague
    statement like "I do have land holding" states no number and correctly
    can't satisfy a > 0 rule on its own."""
    response = _query(
        _cid("prompt-fix"),
        _sid(),
        "Can I get a Kisan Credit Card? I am a farmer, 40 years old.",
    )
    assert response.status_code == 200
    body = response.json()
    assert "has_land_holding" in body["results"][0]["missing"]
    assert "how many acres of land you own" in body["reply_text"]


def test_b_natural_phrasing_fact_resolves_previously_discussed_scheme_without_naming_it():
    """Failure 2: single NOT ELIGIBLE result due to one missing field, then a
    natural-phrasing follow-up supplying that fact WITHOUT naming the scheme.
    Must re-evaluate the previously-discussed scheme and show updated
    eligibility."""
    session_id = _sid()
    customer_id = _cid("regress-b")

    first = _query(
        customer_id, session_id, "Can I get a Kisan Credit Card? I am a farmer, 40 years old."
    ).json()
    assert first["results"][0]["eligible"] is False
    assert "has_land_holding" in first["results"][0]["missing"]

    second = _query(customer_id, session_id, "Yes, I have about 3 acres of land")
    assert second.status_code == 200
    body = second.json()
    assert body["turn_type"] == "recheck_unresolved"
    assert body["results"][0]["scheme_id"] == "kisan_credit_card"
    assert body["results"][0]["eligible"] is True


def test_c_fact_with_nothing_discussed_yet_returns_acknowledgment_not_error():
    response = _query(_cid("regress-c"), _sid(), "I have a girl who is 8")
    assert response.status_code == 200
    body = response.json()
    assert body["turn_type"] == "acknowledgment"
    assert body["results"] == []
    assert "has_girl_child_under_10" in body["facts_updated"]


def test_d_fact_persists_across_a_new_session_same_customer():
    customer_id = _cid("regress-d")

    _query(customer_id, _sid(), "I have a girl who is 8")

    fresh_session = _sid()
    response = _query(
        customer_id, fresh_session, "Can I open a Sukanya Samriddhi account? I am 30."
    )
    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["eligible"] is True
    assert "girl_child_under_10" in body["results"][0]["satisfied"]
