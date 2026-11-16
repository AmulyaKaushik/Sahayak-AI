"""Auth, server-issued sessions and ownership checks. Postgres/Redis are
replaced with in-memory fakes (tests/fakes.py); the real LLM pipeline is
replaced by a stub orchestrator."""

import pytest
from fastapi.testclient import TestClient

from main import app
from security.auth import create_access_token
from tests.fakes import install_fake_auth_backend

client = TestClient(app)


@pytest.fixture(autouse=True)
def fake_backend(monkeypatch):
    install_fake_auth_backend(monkeypatch)


def _register(login_id="9999999999", password="test-pass-123"):
    return client.post("/auth/register", json={"login_id": login_id, "password": password})


def _auth(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_register_returns_tokens_and_customer_id():
    response = _register()
    assert response.status_code == 201
    body = response.json()
    assert body["customer_id"] and body["access_token"] and body["refresh_token"]
    assert body["profile_completed"] is False


def test_duplicate_register_is_409():
    _register()
    assert _register().status_code == 409


def test_wrong_password_is_401_and_right_password_works():
    _register()
    bad = client.post("/auth/login", json={"login_id": "9999999999", "password": "wrong-password"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "unauthorized"
    good = client.post("/auth/login", json={"login_id": "9999999999", "password": "test-pass-123"})
    assert good.status_code == 200


def test_login_rate_limit_returns_429():
    _register()
    codes = [
        client.post("/auth/login", json={"login_id": "9999999999", "password": "wrong-password"}).status_code
        for _ in range(8)
    ]
    assert 429 in codes


def test_refresh_rotates_and_old_refresh_token_is_rejected():
    tokens = _register().json()
    first = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert first.status_code == 200
    replay = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401


def test_refresh_token_cannot_be_used_as_access_token():
    tokens = _register().json()
    response = client.post(
        "/api/v1/sessions", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
    )
    assert response.status_code == 401


def test_access_token_cannot_be_used_to_refresh():
    tokens = _register().json()
    assert client.post("/auth/refresh", json={"refresh_token": tokens["access_token"]}).status_code == 401


def test_sessions_require_a_token():
    assert client.post("/api/v1/sessions").status_code == 401


def test_session_owned_by_other_customer_is_403(monkeypatch):
    import sahayak_ai.api as chat_api
    from sahayak_ai.models import SahayakResponse

    async def fake_handle(customer_id, session_id, text, language):
        return SahayakResponse(
            reply_text=f"hi {customer_id}", display_text="hi", language=language, turn_type="information"
        )

    monkeypatch.setattr(chat_api, "handle_message", fake_handle)

    a = _register("alice@example.com").json()
    b = _register("bob@example.com").json()
    session_id = client.post("/api/v1/sessions", headers=_auth(a)).json()["session_id"]

    body = {"text": "hello", "language": "en-IN"}
    own = client.post(f"/api/v1/sessions/{session_id}/messages", json=body, headers=_auth(a))
    assert own.status_code == 200
    assert own.json()["reply_text"] == f"hi {a['customer_id']}"

    other = client.post(f"/api/v1/sessions/{session_id}/messages", json=body, headers=_auth(b))
    assert other.status_code == 403

    unknown = client.post("/api/v1/sessions/not-a-session/messages", json=body, headers=_auth(a))
    assert unknown.status_code == 403


def test_expired_or_garbage_token_is_401():
    assert client.post("/api/v1/sessions", headers={"Authorization": "Bearer garbage"}).status_code == 401
    expired = create_access_token("someone", expires_minutes=-1)
    assert client.post("/api/v1/sessions", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_admin_endpoints_need_the_admin_key():
    assert client.get("/api/v1/admin/documents").status_code in (401, 403)
    assert client.get("/api/v1/admin/documents", headers={"X-Admin-Key": "nope"}).status_code == 401
    assert client.get("/health/deps").status_code in (401, 403)


def test_health_is_public_on_both_paths():
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/v1/health").json() == {"status": "ok"}
