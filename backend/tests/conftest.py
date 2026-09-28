import pytest

from eligibility_engine.seed import seed_all


@pytest.fixture(scope="session", autouse=True)
def seeded_eligibility_rules():
    seed_all()
