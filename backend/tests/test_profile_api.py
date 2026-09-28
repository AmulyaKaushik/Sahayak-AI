import uuid

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_versioned_upsert_keeps_old_value():
    customer_id = f"cust-versioning-test-{uuid.uuid4()}"

    first = {
        "customer_id": customer_id,
        "monthly_income": 20000,
        "age": 30,
        "dependents": 1,
        "employment_type": "salaried",
        "existing_products": [],
        "language_preference": "hi",
    }
    response = client.put(f"/profiles/{customer_id}", json=first)
    assert response.status_code == 200

    second = dict(first, monthly_income=25000)
    response = client.put(f"/profiles/{customer_id}", json=second)
    assert response.status_code == 200
    assert response.json()["monthly_income"] == 25000

    history_response = client.get(f"/profiles/{customer_id}/history/monthly_income")
    assert history_response.status_code == 200
    records = history_response.json()
    assert len(records) == 1
    assert records[0]["value"] == 20000

    current = client.get(f"/profiles/{customer_id}")
    assert current.json()["monthly_income"] == 25000


def test_missing_profile_returns_404():
    response = client.get(f"/profiles/cust-does-not-exist-{uuid.uuid4()}")
    assert response.status_code == 404
