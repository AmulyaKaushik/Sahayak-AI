"""Deterministic, code-level guard against a worker's narration contradicting
the engine's verdict (Section 2, constraint #2: workers narrate, they never
decide). This is a plain-text lint, not an LLM call, and it runs on every
narration before it's returned to the supervisor.

Not to be confused with the Phase 10 offline template-narration fallback
(Section 4.8) -- that fallback fires when the LLM is unreachable at all.
This guard fires when the LLM answered but its prose contradicts the
structured verdict, and falls back to a minimal deterministic sentence
built only from the structured fields."""

_POSITIVE_PHRASES = ("you are eligible", "you qualify", "you're eligible")
_NEGATIVE_PHRASES = ("not eligible", "don't qualify", "do not qualify", "aren't eligible", "you're not eligible")


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
    verdict = "you are eligible" if eligible else "you are not yet eligible"
    sentence = f"Based on our records, {verdict} for {scheme_or_loan_name}."
    if satisfied:
        sentence += f" Requirements met: {', '.join(satisfied)}."
    if missing:
        sentence += f" Still needed: {', '.join(missing)}."
    return sentence
