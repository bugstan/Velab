from __future__ import annotations

from datetime import datetime, timezone


def _session_payload(session_id: str = "session-test-1") -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": session_id,
        "title": "测试会话",
        "messages": [
            {
                "id": "m1",
                "role": "user",
                "content": "hello",
                "timestamp": now,
            },
            {
                "id": "m2",
                "role": "assistant",
                "content": "world",
                "timestamp": now,
                "thinking": {"steps": [], "isExpanded": False},
            },
        ],
        "createdAt": now,
        "updatedAt": now,
        "titleSource": "manual",
        "titleAutoOptimized": False,
        "turnCount": 1,
    }


def test_upsert_and_get_session(client):
    payload = _session_payload("session-test-1")
    upsert = client.put("/api/sessions/session-test-1", json=payload)
    assert upsert.status_code == 200
    assert upsert.json()["id"] == "session-test-1"

    detail = client.get("/api/sessions/session-test-1")
    assert detail.status_code == 200
    body = detail.json()
    assert body["title"] == "测试会话"
    assert len(body["messages"]) == 2
    assert body["messages"][1]["content"] == "world"


def test_list_and_delete_session(client):
    payload = _session_payload("session-test-2")
    client.put("/api/sessions/session-test-2", json=payload)

    listed = client.get("/api/sessions")
    assert listed.status_code == 200
    rows = listed.json()
    assert any(row["id"] == "session-test-2" for row in rows)

    deleted = client.delete("/api/sessions/session-test-2")
    assert deleted.status_code == 204

    detail = client.get("/api/sessions/session-test-2")
    assert detail.status_code == 404
