"""Seeds a handful of realistic CustomerProfile rows via
db_manager.repository.upsert_profile so /api/v1/query has real data to run
against instead of only the "no profile found" fallback path.

Only CustomerProfile-native fields are seeded -- scheme-specific extra
fields (has_girl_child_under_10, owns_pucca_house, etc.) have nowhere to
persist (see the profile-store gap noted in this task's scope) and are
supplied per-query via the request's extra_fields instead.

Run: python -m scripts.seed_sample_profiles
"""

from db_manager.repository import upsert_profile
from schemas.models import CustomerProfile

SAMPLE_PROFILES = [
    (
        "cust-101",
        "Deepak -- eligible for a loan AND a scheme purely via CustomerProfile-native fields "
        "(retail_micro_loan AND pm_jan_dhan_yojana)",
        CustomerProfile(
            customer_id="cust-101",
            monthly_income=20000,
            age=35,
            dependents=2,
            employment_type="salaried",
            existing_products=[],
            language_preference="en",
        ),
    ),
    (
        "cust-102",
        "Asha -- missing 2 required fields for retail_micro_loan (employment_type, monthly_income unknown)",
        CustomerProfile(
            customer_id="cust-102",
            monthly_income=None,
            age=25,
            dependents=1,
            employment_type=None,
            existing_products=[],
            language_preference="hi",
        ),
    ),
    (
        "cust-103",
        "Vikram -- hard-fails senior_citizen_savings_scheme outright (age known and too low, not just unknown)",
        CustomerProfile(
            customer_id="cust-103",
            monthly_income=None,
            age=15,
            dependents=0,
            employment_type=None,
            existing_products=[],
            language_preference="en",
        ),
    ),
]


def main() -> None:
    for customer_id, label, profile in SAMPLE_PROFILES:
        upsert_profile(profile, source="seed_sample_profiles")
        print(f"seeded {customer_id} ({label})")


if __name__ == "__main__":
    main()
