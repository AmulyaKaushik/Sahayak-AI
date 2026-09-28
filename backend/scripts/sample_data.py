"""Sample data for manually exercising the backend end-to-end. Not part of
the architecture doc's phases -- dev/demo tooling only.

Each entry pairs a CustomerProfile with the scheme it's meant to demonstrate
and any supplementary fields the scheme's rule needs beyond CustomerProfile's
fixed 6 fields (e.g. has_girl_child_under_10) -- see the docstring in
eligibility_engine/rules_seed.py for why those extra fields exist.
"""

from schemas.models import CustomerProfile

SAMPLE_CASES = [
    {
        "label": "Meena -- eligible for Sukanya Samriddhi (girl child under 10)",
        "profile": CustomerProfile(
            customer_id="cust-001",
            monthly_income=18000,
            age=32,
            dependents=1,
            employment_type="salaried",
            existing_products=[],
            language_preference="hi",
        ),
        "scheme_id": "sukanya_samriddhi",
        "extra_fields": {"has_girl_child_under_10": True},
    },
    {
        "label": "Ramesh -- eligible for PM Jan Dhan Yojana (no existing basic account)",
        "profile": CustomerProfile(
            customer_id="cust-002",
            monthly_income=None,
            age=22,
            dependents=0,
            employment_type=None,
            existing_products=[],
            language_preference="hi",
        ),
        "scheme_id": "pm_jan_dhan_yojana",
        "extra_fields": {},
    },
    {
        "label": "Suresh -- eligible for PMAY rural housing subsidy",
        "profile": CustomerProfile(
            customer_id="cust-003",
            monthly_income=15000,
            age=29,
            dependents=3,
            employment_type="daily_wage",
            existing_products=[],
            language_preference="mr",
        ),
        "scheme_id": "pmay_rural_housing_subsidy",
        "extra_fields": {"owns_pucca_house": False, "is_first_time_home_buyer": True},
    },
    {
        "label": "Ganpat -- eligible for Kisan Credit Card",
        "profile": CustomerProfile(
            customer_id="cust-004",
            monthly_income=12000,
            age=50,
            dependents=4,
            employment_type="farmer",
            existing_products=[],
            language_preference="mr",
        ),
        "scheme_id": "kisan_credit_card",
        "extra_fields": {"land_holding_acres": 3.0},
    },
    {
        "label": "Priya -- eligible for the retail micro loan (salaried branch of the OR group)",
        "profile": CustomerProfile(
            customer_id="cust-005",
            monthly_income=25000,
            age=35,
            dependents=2,
            employment_type="salaried",
            existing_products=[],
            language_preference="en",
        ),
        "scheme_id": "retail_micro_loan",
        "extra_fields": {},
    },
    {
        "label": "Krishnan -- eligible for the Senior Citizen Savings Scheme",
        "profile": CustomerProfile(
            customer_id="cust-006",
            monthly_income=8000,
            age=68,
            dependents=0,
            employment_type=None,
            existing_products=[],
            language_preference="ta",
        ),
        "scheme_id": "senior_citizen_savings_scheme",
        "extra_fields": {},
    },
    {
        "label": "Anita -- NOT eligible for PMAY (income above the bracket) -- negative case",
        "profile": CustomerProfile(
            customer_id="cust-007",
            monthly_income=70000,
            age=45,
            dependents=1,
            employment_type="salaried",
            existing_products=[],
            language_preference="en",
        ),
        "scheme_id": "pmay_rural_housing_subsidy",
        "extra_fields": {"owns_pucca_house": False, "is_first_time_home_buyer": True},
    },
    {
        "label": "Farida -- PARTIALLY eligible for Sukanya Samriddhi (girl-child fact not yet known)",
        "profile": CustomerProfile(
            customer_id="cust-008",
            monthly_income=None,
            age=28,
            dependents=1,
            employment_type=None,
            existing_products=[],
            language_preference="ur",
        ),
        "scheme_id": "sukanya_samriddhi",
        "extra_fields": {},
    },
    {
        "label": "Irfan -- eligible for PM Mudra Yojana (Shishu) micro-business loan",
        "profile": CustomerProfile(
            customer_id="cust-009",
            monthly_income=None,
            age=27,
            dependents=0,
            employment_type="self_employed",
            existing_products=[],
            language_preference="hi",
        ),
        "scheme_id": "pm_mudra_yojana_shishu",
        "extra_fields": {"has_business_plan": True},
    },
    {
        "label": "Kavita -- eligible for a regular Home Loan (distinct from the PMAY subsidy)",
        "profile": CustomerProfile(
            customer_id="cust-010",
            monthly_income=45000,
            age=33,
            dependents=1,
            employment_type="self_employed",
            existing_products=[],
            language_preference="en",
        ),
        "scheme_id": "home_loan",
        "extra_fields": {"has_property_papers": True},
    },
    {
        "label": "Naveen -- NOT eligible for Atal Pension Yojana (government employee) -- negative case",
        "profile": CustomerProfile(
            customer_id="cust-011",
            monthly_income=None,
            age=25,
            dependents=0,
            employment_type="government_employee",
            existing_products=[],
            language_preference="ta",
        ),
        "scheme_id": "atal_pension_yojana",
        "extra_fields": {},
    },
]
