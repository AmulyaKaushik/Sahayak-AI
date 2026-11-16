"""Pure-logic tests for the Sahayak_AI layer, chunking and passwords. No LLM,
DB or Redis."""

import pytest

from eligibility_agent.agent import EligibilityOutput
from rag.agent import RagAnswer, RagSource
from rag.chunking import chunk_pages
from rag.extract import Page
from sahayak_ai import refiner, router
from sahayak_ai.models import AgentOutput
from security.passwords import hash_password, verify_password
from supervisor.agent import SchemeResult


def test_password_hash_roundtrip_and_salting():
    h1, h2 = hash_password("correct horse"), hash_password("correct horse")
    assert h1 != h2
    assert verify_password("correct horse", h1)
    assert not verify_password("wrong", h1)
    assert not verify_password("x", "garbage")


@pytest.mark.parametrize(
    "text,agent",
    [
        ("Am I eligible for the PM loan?", "eligibility"),
        ("What is the minimum age of the daughter?", "rag"),
        ("I have a daughter who is 17", "eligibility"),
        ("Can I get a retail micro loan?", "eligibility"),
        ("Why is there a minimum age for this loan?", "rag"),
    ],
)
def test_fallback_plan_routes_the_example_sentences(text, agent):
    plan = router.fallback_plan(text, "home_loan")
    assert [t.agent for t in plan.subtasks] == [agent]
    assert plan.subtasks[0].scheme_id == "home_loan"


def test_clean_drops_unknown_scheme_ids_and_fills_blank_text():
    plan = router._clean(
        [{"agent": "rag", "text": " ", "scheme_id": "made_up"}, {"agent": "bogus", "text": "x"}],
        "original",
        "home_loan",
    )
    assert len(plan.subtasks) == 1
    assert plan.subtasks[0].text == "original"
    # An unknown id is dropped, not replaced by the active scheme: the model
    # already resolves "this loan" itself, and filling it in here would pin
    # "which loans am I eligible for" to whatever was discussed last.
    assert plan.subtasks[0].scheme_id is None


def test_clean_keeps_a_known_scheme_id_and_has_question():
    plan = router._clean(
        [{"agent": "eligibility", "text": "I am 30", "scheme_id": "home_loan", "has_question": False}],
        "I am 30",
        "kisan_credit_card",
    )
    assert plan.subtasks[0].scheme_id == "home_loan"
    assert plan.subtasks[0].has_question is False


def test_fallback_plan_does_not_pin_all_loans_questions_to_the_active_scheme():
    plan = router.fallback_plan("Which loans am I eligible for?", "home_loan")
    assert plan.subtasks[0].scheme_id is None
    assert plan.subtasks[0].has_question is True
    statement = router.fallback_plan("I have a daughter who is 17", "home_loan")
    assert statement.subtasks[0].has_question is False


def _elig(reply, eligible=False):
    return AgentOutput(
        agent="eligibility",
        eligibility=EligibilityOutput(
            reply_text=reply,
            results=[
                SchemeResult(
                    scheme_id="home_loan", eligible=eligible, satisfied=[], missing=["has_property_papers"]
                )
            ],
        ),
    )


async def test_refiner_english_eligibility_is_deterministic_and_clean():
    out = _elig(
        "Based on our records, you are not yet eligible for home_loan. "
        "Still needed: has_property_papers. Income Rs 25,000."
    )
    refined = await refiner.refine([out], "en-IN")
    assert "_" not in refined.speech_text
    assert "25,000 rupees" in refined.speech_text
    assert "not yet eligible" in refined.speech_text


async def test_refiner_rag_without_answer_says_so():
    refined = await refiner.refine([AgentOutput(agent="rag", rag=RagAnswer(answer=None))], "en-IN")
    assert "could not find" in refined.speech_text


async def test_refiner_rejects_llm_output_that_changes_a_number(monkeypatch):
    out = AgentOutput(
        agent="rag",
        rag=RagAnswer(
            answer="The minimum age is 8 years.",
            sources=[RagSource(doc="pm.pdf", page=2)],
            confidence="high",
        ),
    )
    monkeypatch.setattr(refiner, "_refine_sync", lambda facts, language: "The minimum age is 18 years.")
    refined = await refiner.refine([out], "en-IN")
    assert "8 years" in refined.speech_text and "18" not in refined.speech_text
    assert "pm.pdf p.2" in refined.display_text


async def test_refiner_accepts_a_faithful_translation(monkeypatch):
    out = AgentOutput(agent="rag", rag=RagAnswer(answer="The minimum age is 8 years.", confidence="high"))
    monkeypatch.setattr(refiner, "_refine_sync", lambda facts, language: "न्यूनतम आयु 8 वर्ष है।")
    refined = await refiner.refine([out], "hi-IN")
    assert refined.speech_text == "न्यूनतम आयु 8 वर्ष है।"


async def test_english_replies_never_call_the_llm(monkeypatch):
    def boom(facts, language):
        raise AssertionError("LLM must not be called for an English reply")

    monkeypatch.setattr(refiner, "_refine_sync", boom)
    out = AgentOutput(agent="rag", rag=RagAnswer(answer="The minimum age is 8 years.", confidence="high"))
    refined = await refiner.refine([out], "en-IN")
    assert refined.speech_text == "The minimum age is 8 years."


def test_guard_rejects_a_flipped_verdict():
    out = _elig("You are not eligible for home_loan.", eligible=False)
    assert not refiner._preserves_facts(
        "You are eligible for home loan.", "You are not eligible for home loan.", [out], "en-IN"
    )
    assert refiner._preserves_facts(
        "Sorry, you are not eligible for home loan.", "You are not eligible for home loan.", [out], "en-IN"
    )


def test_chunking_keeps_sections_and_pages():
    text = (
        "ELIGIBILITY CRITERIA\n"
        + "\n".join(f"Condition {i} applies to the applicant." for i in range(200))
        + "\nBENEFITS\nA grant."
    )
    chunks = chunk_pages([Page(1, text), Page(2, "DOCUMENTS REQUIRED\nAadhaar card")])
    assert chunks[0].section == "ELIGIBILITY CRITERIA"
    assert any(c.section == "BENEFITS" and "grant" in c.content for c in chunks)
    assert chunks[-1].page == 2 and chunks[-1].section == "DOCUMENTS REQUIRED"
    assert all(len(c.content) < 3500 for c in chunks)


def test_humanize_rupee_amounts_read_naturally():
    from sahayak_ai.refiner import humanize

    assert humanize("pension of ₹1,000, ₹2,000 or Rs. 5,000.") == "pension of 1,000 rupees, 2,000 rupees or 5,000 rupees."
    assert humanize("subsidy of ₹1.20 lakh per house") == "subsidy of 1.20 lakh rupees per house"
    assert humanize("limit INR 3 lakh") == "limit 3 lakh rupees"


def test_messages_with_secrets_are_refused_before_any_processing():
    import asyncio

    from sahayak_ai import orchestrator

    for text in ("my PIN is 1234", "the OTP is 556677", "card 1234 5678 9012 3456"):
        reply = asyncio.run(orchestrator.handle_message("c1", "s1", text, "en-IN"))
        assert reply.reply_text == orchestrator.SECRET_REPLY
    assert not orchestrator._SECRET.search("I want a home loan to pin down my budget"[:10] + " pinned")
