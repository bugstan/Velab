"""Tests for the /api/feedback CRUD endpoints.

Uses the shared test_db + client fixtures from conftest.py, which override
the FastAPI dependency with an in-memory SQLite DB.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_PAYLOAD = {
    "case_id": "test_case_001",
    "root_cause": "校验失败导致升级中断",
    "confidence": 0.85,
    "recommendations": ["增加重试次数", "检查网络稳定性"],
    "confirmed_by": "engineer@example.com",
    "confirmation_status": "CONFIRMED",
    "engineer_notes": "复现了两次，根因明确",
    "evidence_log_ids": [1, 2],
    "evidence_jira_ids": ["FOTA-123"],
    "evidence_doc_ids": [],
    "metadata": {"severity": "high"},
}


# ---------------------------------------------------------------------------
# POST /api/feedback — submit
# ---------------------------------------------------------------------------

class TestSubmitFeedback:
    def test_submit_returns_201(self, client, sample_case):
        r = client.post("/api/feedback", json=_VALID_PAYLOAD)
        assert r.status_code == 201

    def test_submit_response_contains_id(self, client, sample_case):
        r = client.post("/api/feedback", json=_VALID_PAYLOAD)
        body = r.json()
        assert "id" in body
        assert body["case_id"] == "test_case_001"

    def test_submit_unknown_case_returns_404(self, client):
        payload = {**_VALID_PAYLOAD, "case_id": "nonexistent_case"}
        r = client.post("/api/feedback", json=payload)
        assert r.status_code == 404

    def test_submit_invalid_status_returns_400(self, client, sample_case):
        payload = {**_VALID_PAYLOAD, "confirmation_status": "INVALID"}
        r = client.post("/api/feedback", json=payload)
        assert r.status_code == 400

    def test_submit_confidence_out_of_range_returns_422(self, client, sample_case):
        payload = {**_VALID_PAYLOAD, "confidence": 1.5}
        r = client.post("/api/feedback", json=payload)
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/feedback/case/{case_id}
# ---------------------------------------------------------------------------

class TestGetCaseFeedback:
    def test_returns_list_for_existing_case(self, client, sample_case):
        # seed two feedbacks
        client.post("/api/feedback", json=_VALID_PAYLOAD)
        client.post("/api/feedback", json={**_VALID_PAYLOAD, "confirmation_status": "REJECTED"})
        r = client.get("/api/feedback/case/test_case_001")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list)
        assert len(body) == 2

    def test_returns_empty_list_for_case_with_no_feedback(self, client, sample_case):
        r = client.get("/api/feedback/case/test_case_001")
        assert r.status_code == 200
        assert r.json() == []


# ---------------------------------------------------------------------------
# GET /api/feedback/{feedback_id}
# ---------------------------------------------------------------------------

class TestGetFeedbackById:
    def test_returns_feedback_for_valid_id(self, client, sample_case):
        create_r = client.post("/api/feedback", json=_VALID_PAYLOAD)
        fid = create_r.json()["id"]
        r = client.get(f"/api/feedback/{fid}")
        assert r.status_code == 200
        assert r.json()["id"] == fid

    def test_returns_404_for_missing_id(self, client):
        r = client.get("/api/feedback/99999")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/feedback — list with pagination
# ---------------------------------------------------------------------------

class TestListFeedback:
    def test_returns_all_feedback(self, client, sample_case):
        client.post("/api/feedback", json=_VALID_PAYLOAD)
        client.post("/api/feedback", json=_VALID_PAYLOAD)
        r = client.get("/api/feedback")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_pagination_limit_respected(self, client, sample_case):
        for _ in range(5):
            client.post("/api/feedback", json=_VALID_PAYLOAD)
        r = client.get("/api/feedback?limit=3")
        assert r.status_code == 200
        assert len(r.json()) == 3


# ---------------------------------------------------------------------------
# GET /api/feedback/stats/summary
# ---------------------------------------------------------------------------

class TestFeedbackStats:
    def test_stats_endpoint_exists_and_returns_200(self, client, sample_case):
        client.post("/api/feedback", json=_VALID_PAYLOAD)
        r = client.get("/api/feedback/stats/summary")
        assert r.status_code == 200

    def test_stats_total_count(self, client, sample_case):
        client.post("/api/feedback", json=_VALID_PAYLOAD)
        client.post("/api/feedback", json={**_VALID_PAYLOAD, "confirmation_status": "REJECTED"})
        body = client.get("/api/feedback/stats/summary").json()
        assert body.get("total") == 2

    def test_stats_confirmed_count(self, client, sample_case):
        client.post("/api/feedback", json=_VALID_PAYLOAD)  # CONFIRMED
        client.post("/api/feedback", json={**_VALID_PAYLOAD, "confirmation_status": "REJECTED"})
        body = client.get("/api/feedback/stats/summary").json()
        assert body.get("confirmed") == 1
