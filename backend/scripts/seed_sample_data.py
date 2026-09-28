"""Seeds the 6 eligibility rules (Phase 2) plus sample customer profiles into
Postgres, so the running system has real data to query against. Requires
Postgres to be up and migrated (database/migrate.py) first.

Run: python -m scripts.seed_sample_data
"""

from db_manager.repository import upsert_profile
from eligibility_engine.seed import seed_all
from scripts.sample_data import SAMPLE_CASES


def main() -> None:
    scheme_ids = seed_all()
    print(f"seeded {len(scheme_ids)} eligibility rules: {', '.join(scheme_ids)}")

    seen_customers = set()
    for case in SAMPLE_CASES:
        profile = case["profile"]
        if profile.customer_id in seen_customers:
            continue
        seen_customers.add(profile.customer_id)
        upsert_profile(profile, source="sample_data_seed")
        print(f"seeded profile {profile.customer_id} ({case['label']})")


if __name__ == "__main__":
    main()
