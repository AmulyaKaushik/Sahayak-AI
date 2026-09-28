"""Hand-encoded rule configs for 6 real, distinct schemes/loan products
(Phase 2 deliverable -- deterministic eligibility is the core differentiator,
so this is invested in for real rather than covering just one scheme).

EligibilityRule.conditions is a top-level list of nodes, implicitly AND-ed
together (eligibility_engine.conditions.evaluate_tree). Each TOP-LEVEL node
carries an "id" -- the requirement label reported in EligibilityResult's
satisfied[]/missing[] -- whether it's a leaf or a group:
    leaf:  {"id": ..., "field": <name looked up in known_fields>, "op": ..., "value": ...}
    group: {"id": ..., "op": "AND" | "OR", "conditions": [<node>, ...]}
Nested children inside a group's "conditions" don't carry their own "id":
satisfied/missing is reported per top-level requirement, not per nested leaf,
so an OR-group's two branches don't show up as one "satisfied" and one
"missing" label when only one branch is actually true.

known_fields is not limited to CustomerProfile's stored attributes -- it also
covers scheme-specific supplementary facts (e.g. has_girl_child_under_10,
land_holding_acres) collected during the conversation, consistent with the
required-fields registry (Section 4.4) tracking arbitrary field names per
scheme, not just the fixed CustomerProfile schema.
"""

from datetime import datetime, timezone

from schemas.models import EligibilityRule

_NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)
_APPROVER = "branch_manager_seed"

RULES: list[EligibilityRule] = [
    EligibilityRule(
        scheme_id="sukanya_samriddhi",
        version=1,
        conditions=[
            {"id": "girl_child_under_10", "field": "has_girl_child_under_10", "op": "==", "value": True},
            {"id": "guardian_age_requirement", "field": "age", "op": ">=", "value": 18},
        ],
        source_document="sukanya_samriddhi_scheme_notification_2019.pdf",
        approved_by=_APPROVER,
        updated_at=_NOW,
    ),
    EligibilityRule(
        scheme_id="pm_jan_dhan_yojana",
        version=1,
        conditions=[
            {"id": "minimum_age", "field": "age", "op": ">=", "value": 10},
            {"id": "no_existing_basic_account", "field": "existing_products", "op": "not_in", "value": "jan_dhan_account"},
        ],
        source_document="pmjdy_guidelines.pdf",
        approved_by=_APPROVER,
        updated_at=_NOW,
    ),
    EligibilityRule(
        scheme_id="pmay_rural_housing_subsidy",
        version=1,
        conditions=[
            {"id": "income_bracket", "field": "monthly_income", "op": "<=", "value": 25000},
            {"id": "no_pucca_house", "field": "owns_pucca_house", "op": "==", "value": False},
            {"id": "first_time_buyer", "field": "is_first_time_home_buyer", "op": "==", "value": True},
        ],
        source_document="pmay_gramin_guidelines.pdf",
        approved_by=_APPROVER,
        updated_at=_NOW,
    ),
    EligibilityRule(
        scheme_id="kisan_credit_card",
        version=1,
        conditions=[
            {"id": "is_farmer", "field": "employment_type", "op": "==", "value": "farmer"},
            {"id": "has_land_holding", "field": "land_holding_acres", "op": ">", "value": 0},
            {"id": "min_age", "field": "age", "op": ">=", "value": 18},
            {"id": "max_age", "field": "age", "op": "<=", "value": 75},
        ],
        source_document="kcc_scheme_circular.pdf",
        approved_by=_APPROVER,
        updated_at=_NOW,
    ),
    EligibilityRule(
        scheme_id="retail_micro_loan",
        version=1,
        conditions=[
            {
                "id": "employment_type_requirement",
                "op": "OR",
                "conditions": [
                    {"field": "employment_type", "op": "==", "value": "salaried"},
                    {"field": "employment_type", "op": "==", "value": "self_employed"},
                ],
            },
            {"id": "minimum_income", "field": "monthly_income", "op": ">=", "value": 15000},
            {"id": "min_age", "field": "age", "op": ">=", "value": 21},
            {"id": "max_age", "field": "age", "op": "<=", "value": 60},
            {"id": "dependents_cap", "field": "dependents", "op": "<=", "value": 6},
        ],
        source_document="retail_micro_loan_product_policy.pdf",
        approved_by=_APPROVER,
        updated_at=_NOW,
    ),
    EligibilityRule(
        scheme_id="senior_citizen_savings_scheme",
        version=1,
        conditions=[
            {"id": "minimum_age_60", "field": "age", "op": ">=", "value": 60},
        ],
        source_document="scss_rules_2019.pdf",
        approved_by=_APPROVER,
        updated_at=_NOW,
    ),
    EligibilityRule(
        scheme_id="pm_mudra_yojana_shishu",
        version=1,
        conditions=[
            {"id": "is_self_employed", "field": "employment_type", "op": "==", "value": "self_employed"},
            {"id": "min_age", "field": "age", "op": ">=", "value": 18},
            {"id": "max_age", "field": "age", "op": "<=", "value": 65},
            {"id": "has_business_plan", "field": "has_business_plan", "op": "==", "value": True},
        ],
        source_document="pmmy_shishu_guidelines.pdf",
        approved_by=_APPROVER,
        updated_at=_NOW,
    ),
    EligibilityRule(
        scheme_id="home_loan",
        version=1,
        conditions=[
            {
                "id": "employment_type_requirement",
                "op": "OR",
                "conditions": [
                    {"field": "employment_type", "op": "==", "value": "salaried"},
                    {"field": "employment_type", "op": "==", "value": "self_employed"},
                ],
            },
            {"id": "minimum_income", "field": "monthly_income", "op": ">=", "value": 30000},
            {"id": "min_age", "field": "age", "op": ">=", "value": 21},
            {"id": "max_age", "field": "age", "op": "<=", "value": 65},
            {"id": "has_property_papers", "field": "has_property_papers", "op": "==", "value": True},
        ],
        source_document="retail_home_loan_product_policy.pdf",
        approved_by=_APPROVER,
        updated_at=_NOW,
    ),
    EligibilityRule(
        scheme_id="atal_pension_yojana",
        version=1,
        conditions=[
            {"id": "min_age", "field": "age", "op": ">=", "value": 18},
            {"id": "max_age", "field": "age", "op": "<=", "value": 40},
            {"id": "not_government_employee", "field": "employment_type", "op": "!=", "value": "government_employee"},
            {"id": "no_existing_apy_account", "field": "existing_products", "op": "not_in", "value": "atal_pension_yojana"},
        ],
        source_document="apy_scheme_details.pdf",
        approved_by=_APPROVER,
        updated_at=_NOW,
    ),
]
