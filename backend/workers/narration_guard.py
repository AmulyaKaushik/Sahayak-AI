"""Deterministic, code-level guard against a worker's narration contradicting
the engine's verdict (Section 2, constraint #2: workers narrate, they never
decide). This is a plain-text lint, not an LLM call, and it runs on every
narration before it's returned to the supervisor.

Not to be confused with the Phase 10 offline template-narration fallback
(Section 4.8) -- that fallback fires when the LLM is unreachable at all.
This guard fires when the LLM answered but its prose contradicts the
structured verdict, and falls back to a minimal deterministic sentence
built only from the structured fields."""

from workers.friendly import join_natural, requirement_label, scheme_name

_POSITIVE_PHRASES = ("you are eligible", "you qualify", "you're eligible")
_NEGATIVE_PHRASES = ("not eligible", "not yet eligible", "don't qualify", "do not qualify", "aren't eligible", "you're not eligible")


def narration_contradicts_verdict(narration: str, eligible: bool) -> bool:
    text = narration.lower()
    claims_positive = any(phrase in text for phrase in _POSITIVE_PHRASES)
    claims_negative = any(phrase in text for phrase in _NEGATIVE_PHRASES)

    if eligible and claims_negative and not claims_positive:
        return True
    if not eligible and claims_positive and not claims_negative:
        return True
    return False


def fallback_narration(scheme_or_loan_name: str, eligible: bool, satisfied: list[str], missing: list[str]) -> str:
    """Plain deterministic sentence from the structured result. Takes raw ids
    and writes customer-friendly names, so nothing like "retail_micro_loan"
    ever reaches the screen or the speaker."""
    name = scheme_name(scheme_or_loan_name)
    if eligible:
        sentence = f"You are eligible for {name}."
    else:
        sentence = f"You are not eligible for {name} yet."
    if satisfied:
        sentence += f" You already meet: {join_natural([requirement_label(r) for r in satisfied])}."
    if missing:
        sentence += f" Not met yet: {join_natural([requirement_label(r) for r in missing])}."
    return sentence
