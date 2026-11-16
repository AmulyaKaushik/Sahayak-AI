"""Key rotation, the no-LLM fallbacks, RAG failure handling, short replies."""

import asyncio
import uuid

from eligibility_agent.agent import EligibilityOutput
from eligibility_engine import rules_repository
from rag import agent as rag_agent
from rag import repository
from rag.embeddings import EmbeddingError
from sahayak_ai import refiner
from sahayak_ai.models import AgentOutput
from supervisor import agent as supervisor
from supervisor.agent import SchemeResult
from supervisor.offline import extract_facts_regex, keyword_target_scheme_ids
from workers import keys


# --- Groq key rotation -------------------------------------------------------

def test_groq_keys_rotate_round_robin(monkeypatch):
    monkeypatch.setattr(keys.settings, "groq_api_key", "k1")
    monkeypatch.setattr(keys.settings, "groq_api_keys", "k2, k3,k1")
    monkeypatch.setattr(keys, "_counter", 0)
    assert keys.groq_keys() == ["k1", "k2", "k3"]
    assert [keys.next_groq_key() for _ in range(5)] == ["k1", "k2", "k3", "k1", "k2"]


def test_no_groq_key_returns_none(monkeypatch):
    monkeypatch.setattr(keys.settings, "groq_api_key", None)
    monkeypatch.setattr(keys.settings, "groq_api_keys", None)
    assert keys.next_groq_key() is None


# --- regex facts -------------------------------------------------------------

def test_regex_facts_cover_the_common_statements():
    assert extract_facts_regex("I earn 40k per month and I am 35 years old") == {
        "age": 35, "monthly_income": 40000}
    assert extract_facts_regex("I have 5 acres of land and I am farmer") == {
        "land_holding_acres": 5, "employment_type": "farmer"}
    assert extract_facts_regex("I earn 6 lakh per year") == {"monthly_income": 50000}
    assert extract_facts_regex("I do not have property papers") == {"has_property_papers": False}
    assert extract_facts_regex("my daughter is 6 years old") == {"has_girl_child_under_10": True}


def test_a_new_amount_is_read_as_income_but_loan_amounts_and_negations_are_not():
    assert extract_facts_regex("I have 6000") == {"monthly_income": 6000}
    assert extract_facts_regex("I want a loan of 500000 rupees") == {}
    assert extract_facts_regex("I am not a farmer") == {}


def test_keyword_targets():
    loans, schemes = ["home_loan", "retail_micro_loan"], ["sukanya_samriddhi", "kisan_credit_card"]
    assert keyword_target_scheme_ids("can I get a kisan credit card", loans, schemes) == ["kisan_credit_card"]
    assert keyword_target_scheme_ids("which loans can I get", loans, schemes) == loans
    assert keyword_target_scheme_ids("loans and schemes", loans, schemes) == loans + schemes
    assert keyword_target_scheme_ids("hello there", loans, schemes) is None


def test_eligibility_works_with_no_llm_and_uses_the_newest_number(monkeypatch):
    def down(*args, **kwargs):
        raise RuntimeError("no internet")

    monkeypatch.setattr(supervisor, "_extract_sync", down)
    monkeypatch.setattr(supervisor, "_resolve_sync", down)
    customer, session = f"offline-{uuid.uuid4()}", str(uuid.uuid4())

    async def ask(text):
        return await supervisor.run_query_pipeline(customer, session, text, has_question=True)

    first = asyncio.run(
        ask("I am 30 years old, salaried, I earn 5000 a month. Am I eligible for a retail micro loan?")
    )
    assert first.results[0].scheme_id == "retail_micro_loan"
    assert "minimum_income" in first.results[0].missing

    second = asyncio.run(ask("I have 60000. Am I eligible for the retail micro loan?"))
    assert "minimum_income" not in second.results[0].missing  # compared with 60000, not 5000


def test_cached_rule_is_used_when_the_database_is_down(monkeypatch):
    rules_repository.clear_rule_cache()
    rule = rules_repository.load_active_rule("home_loan")
    monkeypatch.setattr(rules_repository, "_RULE_TTL_SECONDS", 0)

    def down(scheme_id):
        raise RuntimeError("db down")

    monkeypatch.setattr(rules_repository, "_load_active_rule_from_db", down)
    assert rules_repository.load_active_rule("home_loan") == rule
    rules_repository.clear_rule_cache()


# --- RAG failures ------------------------------------------------------------

_HIT = {"chunk_id": 1, "filename": "home_loan.pdf", "page": 2, "section": None,
        "content": "Tenure up to 30 years.", "similarity": 0.0, "doc_type": "loan", "by_keyword": True}


def test_rag_falls_back_to_keyword_search_when_embedding_fails(monkeypatch):
    def broken(question):
        raise EmbeddingError("429")

    monkeypatch.setattr(rag_agent, "embed_query", broken)
    monkeypatch.setattr(repository, "search_text", lambda d, q, s, n: [_HIT] if d == "loan" else [])

    class Prediction:
        answer, used_passages = "The tenure is up to 30 years.", [1]

    monkeypatch.setattr(rag_agent, "_answer_from_context", lambda **kw: Prediction())
    result = rag_agent._answer_sync("what is the home loan tenure", None, "home_loan")
    assert result.answer and not result.unavailable
    assert result.sources[0].doc == "home_loan.pdf"


def test_llm_failure_is_unavailable_not_not_found(monkeypatch):
    monkeypatch.setattr(rag_agent, "embed_query", lambda q: [0.0] * 768)
    monkeypatch.setattr(
        repository, "search", lambda d, v, s, n: [{**_HIT, "similarity": 0.9, "by_keyword": False}]
    )

    def down(**kwargs):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(rag_agent, "_answer_from_context", down)
    result = rag_agent._answer_sync("tenure?", None, None)
    assert result.answer is None and result.unavailable


def test_database_failure_is_unavailable(monkeypatch):
    monkeypatch.setattr(rag_agent, "embed_query", lambda q: [0.0] * 768)

    def down(*args):
        raise RuntimeError("db")

    monkeypatch.setattr(repository, "search", down)
    assert rag_agent._answer_sync("tenure?", None, None).unavailable


def test_genuinely_not_found_is_not_unavailable(monkeypatch):
    monkeypatch.setattr(rag_agent, "embed_query", lambda q: [0.0] * 768)
    monkeypatch.setattr(repository, "search", lambda d, v, s, n: [])
    result = rag_agent._answer_sync("capital of France?", None, None)
    assert result.answer is None and not result.unavailable


def test_refiner_says_unavailable_not_not_found():
    out = AgentOutput(agent="rag", rag=rag_agent.RagAnswer(answer=None, unavailable=True))
    reply = asyncio.run(refiner.refine([out], "en-IN"))
    assert "trouble" in reply.speech_text and "could not find" not in reply.speech_text


# --- short replies -----------------------------------------------------------

def _result(scheme_id, eligible, missing=(), ask=()):
    return SchemeResult(
        scheme_id=scheme_id, eligible=eligible, satisfied=[], missing=list(missing), ask=list(ask)
    )


def test_many_schemes_become_one_short_reply():
    output = EligibilityOutput(
        reply_text="long text",
        results=[
            _result("home_loan", False, ["has_property_papers"], ["has_property_papers"]),
            _result("kisan_credit_card", True),
            _result("retail_micro_loan", False, ["minimum_income", "dependents_cap", "min_age"], ["dependents"]),
            _result("sukanya_samriddhi", False, ["a", "b", "c"], ["has_girl_child_under_10"]),
        ],
    )
    text = refiner.summarize_eligibility(output)
    assert text.startswith("You are eligible for Kisan Credit Card.")
    assert "You are close on Home Loan, which still needs having the property papers." in text
    assert "2 others" in text and text.count("please tell me") == 1
    assert len(text) < 450


def test_a_stated_fact_gets_a_short_acknowledgement():
    output = EligibilityOutput(
        reply_text="long text",
        turn_type="recheck_unresolved",
        results=[_result("home_loan", False, ["has_property_papers"], ["has_property_papers"])],
    )
    text = refiner.summarize_eligibility(output)
    assert text.startswith("Got it, I've noted that.") and "For Home Loan, please tell me" in text


def test_single_scheme_question_keeps_its_normal_sentence():
    output = EligibilityOutput(reply_text="x", results=[_result("home_loan", False, ["a"])])
    assert refiner.summarize_eligibility(output) is None
