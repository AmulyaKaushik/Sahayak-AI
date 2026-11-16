"""Human-readable names for scheme ids and rule-requirement ids.

The engine and the API keep using the raw ids (they are stable keys); only
text shown or spoken to the customer goes through this module. Unknown ids
(e.g. a scheme added later from a document) still read acceptably: underscores
become spaces."""

import re

SCHEME_NAMES: dict[str, str] = {
    "sukanya_samriddhi": "Sukanya Samriddhi Yojana",
    "pm_jan_dhan_yojana": "PM Jan Dhan Yojana",
    "pmay_rural_housing_subsidy": "PMAY Rural Housing Subsidy",
    "kisan_credit_card": "Kisan Credit Card",
    "retail_micro_loan": "Retail Micro Loan",
    "senior_citizen_savings_scheme": "Senior Citizen Savings Scheme",
    "pm_mudra_yojana_shishu": "PM Mudra Yojana (Shishu)",
    "home_loan": "Home Loan",
    "atal_pension_yojana": "Atal Pension Yojana",
}

# No thresholds here on purpose: they live in the rules (and differ per
# scheme for the same id, e.g. min_age), so a number written here could drift.
REQUIREMENT_LABELS: dict[str, str] = {
    "girl_child_under_10": "having a girl child under 10",
    "guardian_age_requirement": "the guardian's age requirement",
    "minimum_age": "the minimum age",
    "no_existing_basic_account": "not already having a Jan Dhan account",
    "income_bracket": "the income limit",
    "no_pucca_house": "not already owning a pucca house",
    "first_time_buyer": "being a first-time home buyer",
    "is_farmer": "being a farmer",
    "has_land_holding": "owning agricultural land",
    "min_age": "the minimum age",
    "max_age": "the maximum age",
    "employment_type_requirement": "the employment type requirement",
    "minimum_income": "the minimum monthly income",
    "dependents_cap": "the limit on dependents",
    "minimum_age_60": "being at least 60 years old",
    "is_self_employed": "being self-employed",
    "has_business_plan": "having a business plan",
    "has_property_papers": "having the property papers",
    "not_government_employee": "not being a government employee",
    "no_existing_apy_account": "not already having an Atal Pension account",
}

_ID_PATTERN = re.compile(
    r"\b("
    + "|".join(sorted({*SCHEME_NAMES, *REQUIREMENT_LABELS}, key=len, reverse=True))
    + r")\b"
)


def _spaced(identifier: str) -> str:
    return identifier.replace("_", " ").strip()


def scheme_name(scheme_id: str) -> str:
    return SCHEME_NAMES.get(scheme_id) or _spaced(scheme_id).title()


def requirement_label(requirement_id: str) -> str:
    return REQUIREMENT_LABELS.get(requirement_id) or _spaced(requirement_id)


def join_natural(items: list[str]) -> str:
    """["a", "b", "c"] -> "a, b and c" (reads better aloud than a bare list)."""
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"


def friendly_text(text: str) -> str:
    """Replace any known raw id left in a sentence (from any source: worker
    narration, error messages) with its friendly name."""

    def replace(match: re.Match) -> str:
        key = match.group(1)
        return SCHEME_NAMES.get(key) or REQUIREMENT_LABELS[key]

    return _ID_PATTERN.sub(replace, text)
