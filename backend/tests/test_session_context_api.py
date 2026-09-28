import uuid

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_create_and_read_context_entry():
    session_id = f"session-test-{uuid.uuid4()}"
    entry = {
        "session_id": session_id,
        "turn_index": 0,
        "summary": "Customer asked about a loan.",
        "fields_collected_this_session": {"age": 30},
        "workers_called": [],
        "written_by": "supervisor",
    }

    response = client.post(f"/session-context/{session_id}", json=entry)
    assert response.status_code == 200

    response = client.get(f"/session-context/{session_id}")
    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 1
    assert entries[0]["summary"] == "Customer asked about a loan."
