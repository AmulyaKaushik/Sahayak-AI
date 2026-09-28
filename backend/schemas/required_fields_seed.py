"""Hand-authored required-fields registry (Section 4.4), one RequiredFieldsEntry
per scheme_id defined in eligibility_engine/rules_seed.py. required_fields is
every leaf "field" name that scheme's EligibilityRule.conditions reads,
flattening nested group conditions too (see retail_micro_loan's OR group).

Hand-authored the same way rules_seed.py is, deliberately NOT derived at
runtime from the rule tree -- eligibility_engine.rules_repository already has
a dynamic equivalent (get_required_field_names) that Phase 4 used as a
stand-in; this is the real, DB-independent registry this scoped-down
pipeline uses instead.
"""

from schemas.models import RequiredFieldsEntry

REQUIRED_FIELDS_ENTRIES: list[RequiredFieldsEntry] = [
    RequiredFieldsEntry(
        scheme_or_loan_id="sukanya_samriddhi",
        required_fields=["has_girl_child_under_10", "age"],
    ),
    RequiredFieldsEntry(
        scheme_or_loan_id="pm_jan_dhan_yojana",
        required_fields=["age", "existing_products"],
    ),
    RequiredFieldsEntry(
        scheme_or_loan_id="pmay_rural_housing_subsidy",
        required_fields=["monthly_income", "owns_pucca_house", "is_first_time_home_buyer"],
    ),
    RequiredFieldsEntry(
        scheme_or_loan_id="kisan_credit_card",
        required_fields=["employment_type", "land_holding_acres", "age"],
    ),
    RequiredFieldsEntry(
        scheme_or_loan_id="retail_micro_loan",
        # employment_type appears once even though it's the field behind
        # both branches of the OR group ("salaried" / "self_employed").
        required_fields=["employment_type", "monthly_income", "age", "dependents"],
    ),
    RequiredFieldsEntry(
        scheme_or_loan_id="senior_citizen_savings_scheme",
        required_fields=["age"],
    ),
    RequiredFieldsEntry(
        scheme_or_loan_id="pm_mudra_yojana_shishu",
        required_fields=["employment_type", "age", "has_business_plan"],
    ),
    RequiredFieldsEntry(
        scheme_or_loan_id="home_loan",
        required_fields=["employment_type", "monthly_income", "age", "has_property_papers"],
    ),
    RequiredFieldsEntry(
        scheme_or_loan_id="atal_pension_yojana",
        required_fields=["age", "employment_type", "existing_products"],
    ),
]

_BY_SCHEME_ID: dict[str, list[str]] = {
    entry.scheme_or_loan_id: entry.required_fields for entry in REQUIRED_FIELDS_ENTRIES
}


def get_required_fields(scheme_id: str) -> list[str]:
    return _BY_SCHEME_ID.get(scheme_id, [])
