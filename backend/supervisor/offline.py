"""Rule-based fallbacks that need no LLM and no internet.

* extract_facts_regex(text): pulls the customer's facts (age, income, land,
  employment, yes/no facts) out of a message with regular expressions.
* keyword_target_scheme_ids(text, ...): works out which loans/schemes a
  question is about from the words in it.

The pipeline always merges the regex facts under the LLM's (the LLM wins on a
conflict), and uses both of these on their own when the LLM is unreachable.
The eligibility rules themselves are cached in memory (rules_repository), so
a check can still be answered offline: the customer's saved facts are
compared with the rule numbers, and a number in the new message (6000)
replaces the saved one (5000) first.

Money: monthly_income is the only money fact the rules use, so an amount with
no other cue ("I have 6000", "Rs 6000") is read as monthly income, but only
when the sentence is just about having that amount -- never in "a loan of
500000 rupees"."""

import re

from schemas.profile_schema import InvalidProfileValue, get_profile_schema, validate_profile_value

_MULTIPLIERS = {
    "k": 1_000, "thousand": 1_000, "lakh": 100_000, "lakhs": 100_000,
    "lac": 100_000, "lacs": 100_000, "crore": 10_000_000, "crores": 10_000_000,
}
_AMOUNT = r"(?:rs\.?|inr|₹)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|lakhs?|lacs?|crores?)?\b"
_SPECS = None


def _spec(field: str):
    global _SPECS
    if _SPECS is None:
        _SPECS = {s.field: s for s in get_profile_schema()}
    return _SPECS.get(field)


def _to_number(digits: str, unit: str | None) -> float:
    value = float(digits.replace(",", ""))
    return value * _MULTIPLIERS.get((unit or "").lower(), 1)


def _clean_number(value: float):
    return int(value) if float(value).is_integer() else value


def _negated(text: str, start: int) -> bool:
    before = text[max(0, start - 25):start].lower()
    return bool(re.search(r"\b(not|no|never|n't|dont|don't|am not|isn't)\s+(a\s+|an\s+|the\s+|any\s+)?(\w+\s+)?$", before))


_EMPLOYMENT = [
    ("government_employee", r"government (employee|job|servant|service)|govt\.? (employee|job)|sarkari|civil servant"),
    ("farmer", r"\bfarmers?\b|\bfarming\b|\bkisan\b|\bcultivat\w+|\bagricultur\w+ (work|labou?r)"),
    ("self_employed", r"self[- ]?employed|own (a )?(business|shop|store)|run (a |my )?(business|shop|store)|business ?(man|owner)|shopkeeper"),
    ("salaried", r"\bsalaried\b|salary job|private (job|sector)|work(ing)? (in|for|at) (a |an )?(company|firm|mnc|office)|\bemployee\b"),
]

_TRUE_FALSE = {
    "has_property_papers": r"property (papers|documents|docs)",
    "has_business_plan": r"business plan",
    "owns_pucca_house": r"(own|have|got)( a| my)? pucca (house|home)|own( a| my)? (house|home)",
}


def _yes_no(text: str, field: str, noun: str) -> bool | None:
    lowered = text.lower()
    match = re.search(noun, lowered)
    if not match:
        return None
    negative = re.search(
        r"\b(no|not|don't|dont|do not|doesn't|never|without|haven't|have not|yet to)\b.{0,25}" + noun, lowered
    ) or re.search(noun + r".{0,20}\b(not ready|missing|lost|pending)\b", lowered)
    return False if negative else True


def extract_facts_regex(text: str) -> dict:
    facts: dict = {}
    lowered = text.lower()

    # --- age ------------------------------------------------------------
    for pattern in (
        r"\b(\d{1,3})\s*(?:years?|yrs?|yo)\s*old\b",
        r"\bage\s*(?:is|of|:|=)?\s*(\d{1,3})\b",
        r"\baged\s*(\d{1,3})\b",
        r"\bi\s*(?:am|'m|m)\s*(\d{1,3})\b(?!\s*(?:k\b|thousand|lakh|acre|rupee|rs\b|percent|%))",
    ):
        for match in re.finditer(pattern, lowered):
            # "my daughter is 6 years old" is the child's age, not the customer's.
            context = lowered[max(0, match.start() - 35):match.start()]
            if re.search(r"\b(daughter|son|child|kid|girl|boy|wife|husband|mother|father)\b", context):
                continue
            facts["age"] = int(match.group(1))
            break
        if "age" in facts:
            break

    # --- monthly income -------------------------------------------------
    income_cue = re.search(
        r"\b(?:earn(?:ing|s)?|income|salary|make|making|paid|get(?:ting)?|take home|receive)\b[^\d₹]{0,30}" + _AMOUNT,
        lowered,
    )
    amount_match = income_cue
    if not amount_match:
        # "I have 6000" / "I only have Rs 6000 per month": the whole clause is the amount.
        amount_match = re.search(
            r"\bi\s*(?:only\s+|just\s+)?(?:have|got|has)\s+" + _AMOUNT
            + r"(?=\s*(?:rupees|rs\b|inr|per month|a month|monthly|\.|,|\?|!|$))",
            lowered,
        )
    if amount_match:
        value = _to_number(amount_match.group(1), amount_match.group(2))
        tail = lowered[amount_match.end():amount_match.end() + 25]
        if re.search(r"\b(per year|a year|yearly|annual|annum|p\.a)", tail) or "annual" in lowered[max(0, amount_match.start() - 12):amount_match.start()]:
            value /= 12
        if value >= 100:  # smaller numbers are ages, counts, acres...
            facts["monthly_income"] = _clean_number(round(value))

    # --- dependents -----------------------------------------------------
    match = re.search(r"\b(\d{1,2})\s*(?:dependents?|dependants?)\b", lowered) or re.search(
        r"\bdependents?\s*(?:are|is|:|=)?\s*(\d{1,2})\b", lowered
    )
    if match:
        facts["dependents"] = int(match.group(1))
    elif re.search(r"\b(no|zero|without any)\s+(dependents?|dependants?)\b", lowered):
        facts["dependents"] = 0

    # --- land -----------------------------------------------------------
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:acres?|acre)\b", lowered)
    if match:
        facts["land_holding_acres"] = _clean_number(float(match.group(1)))
    elif re.search(r"\b(no|don't have any|do not have any|without)\s+(agricultural\s+)?land\b", lowered):
        facts["land_holding_acres"] = 0

    # --- employment type ------------------------------------------------
    for value, pattern in _EMPLOYMENT:
        match = re.search(pattern, lowered)
        if match and not _negated(lowered, match.start()):
            facts["employment_type"] = value
            break

    # --- yes / no facts -------------------------------------------------
    for field, noun in _TRUE_FALSE.items():
        answer = _yes_no(text, field, noun)
        if answer is not None:
            facts[field] = answer
    if re.search(r"first[- ](time )?(home|house|property)", lowered):
        facts["is_first_time_home_buyer"] = not re.search(r"\bnot\b.{0,15}first", lowered)
    match = re.search(r"\b(?:daughter|girl child|girl)\b[^.?!\d]{0,30}?(\d{1,2})\s*(?:years?|yrs?)", lowered)
    if match:
        facts["has_girl_child_under_10"] = int(match.group(1)) < 10
    elif re.search(r"\b(?:girl child|daughter)\b.{0,25}under (?:10|ten)", lowered):
        facts["has_girl_child_under_10"] = True

    # Only keep values the profile schema accepts.
    valid: dict = {}
    for field, value in facts.items():
        spec = _spec(field)
        if spec is None:
            continue
        try:
            valid[field] = validate_profile_value(spec, value)
        except InvalidProfileValue:
            continue
    return valid


# --- which loans / schemes is the question about ------------------------------

_ALIASES: dict[str, str] = {
    r"home loan|housing loan|house loan|mortgage": "home_loan",
    r"kisan credit|\bkcc\b": "kisan_credit_card",
    r"micro loan|retail loan|retail micro": "retail_micro_loan",
    r"mudra|shishu": "pm_mudra_yojana_shishu",
    r"jan dhan|jandhan|zero balance account|basic savings": "pm_jan_dhan_yojana",
    r"sukanya|samriddhi": "sukanya_samriddhi",
    r"atal pension|\bapy\b": "atal_pension_yojana",
    r"senior citizen|\bscss\b": "senior_citizen_savings_scheme",
    r"pmay|awas|rural housing|housing subsidy": "pmay_rural_housing_subsidy",
}
_LOANS = re.compile(r"\bloans?\b|\bborrow\w*|\bcredit\b", re.I)
_SCHEMES = re.compile(r"\bschemes?\b|\byojana\b|\bsubsid\w+|\bpension\b|\bsavings\b|\bgovernment\b", re.I)
_ANYTHING = re.compile(r"\b(which|what|all|any|every|everything|anything)\b", re.I)


def named_scheme_ids(text: str) -> list[str]:
    """Schemes/loans the text names outright ("Sukanya", "home loan")."""
    return [sid for pattern, sid in _ALIASES.items() if re.search(pattern, text, re.I)]


def keyword_target_scheme_ids(
    text: str, loan_ids: list[str], scheme_ids: list[str], active_scheme_id: str | None = None
) -> list[str] | None:
    """None = cannot tell from the words alone."""
    named = [sid for pattern, sid in _ALIASES.items() if re.search(pattern, text, re.I)]
    known = set(loan_ids) | set(scheme_ids)
    named = [sid for sid in named if sid in known]
    if named:
        return named
    wants_loans, wants_schemes = bool(_LOANS.search(text)), bool(_SCHEMES.search(text))
    if wants_loans and wants_schemes:
        return list(loan_ids) + list(scheme_ids)
    if wants_loans:
        return list(loan_ids)
    if wants_schemes:
        return list(scheme_ids)
    if re.search(r"\b(this|that|it|same)\b", text, re.I) and active_scheme_id in known:
        return [active_scheme_id]
    if _ANYTHING.search(text) and re.search(r"eligib|qualif", text, re.I):
        return list(loan_ids) + list(scheme_ids)
    return None
