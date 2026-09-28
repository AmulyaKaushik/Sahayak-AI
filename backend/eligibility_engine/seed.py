from eligibility_engine.rules_repository import upsert_and_activate
from eligibility_engine.rules_seed import RULES


def seed_all() -> list[str]:
    for rule in RULES:
        upsert_and_activate(rule)
    return [rule.scheme_id for rule in RULES]


if __name__ == "__main__":
    for scheme_id in seed_all():
        print(f"seeded active rule for {scheme_id}")
