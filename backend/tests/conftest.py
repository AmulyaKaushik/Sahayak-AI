import os

# The pre-auth debug routes (/profiles, /session-context, /api/v1/query) are
# off by default; the older test-suites exercise them directly. Must be set
# before `main` (and therefore `settings`) is imported.
os.environ.setdefault("ENABLE_DEBUG_ROUTES", "true")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-123456")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key")

import pytest  # noqa: E402

from eligibility_engine.seed import seed_all  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def seeded_eligibility_rules():
    seed_all()
