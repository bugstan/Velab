"""Tests for the /api/bundles upload endpoint — format validation and
accepted file types (zip, rar, log, txt, dlt).

The IngestPipeline.run() is mocked out so tests don't need a real pipeline.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from log_pipeline.api.http import create_app
from log_pipeline.config import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        store_root=tmp_path / "store",
        upload_root=tmp_path / "uploads",
        work_root=tmp_path / "work",
        index_root=tmp_path / "indexes",
        catalog_db=tmp_path / "catalog.db",
        classifier_yaml=Path("config/controllers.yaml"),
        event_rules_yaml=Path("config/event_rules.yaml"),
        anchor_rules_yaml=Path("config/anchor_rules.yaml"),
        slim_rules_yaml=Path("config/slim_rules.yaml"),
    )


def _client(tmp_path: Path) -> TestClient:
    """Return a TestClient whose pipeline.run() is mocked to a no-op."""
    s = _settings(tmp_path)
    app = create_app(s)
    # Patch at the class level so the single instance inside app.state is covered.
    patcher_run = patch("log_pipeline.ingest.pipeline.IngestPipeline.run", return_value={})
    patcher_run.start()
    client = TestClient(app)
    client._patcher_run = patcher_run  # type: ignore[attr-defined]
    return client


# ---------------------------------------------------------------------------
# Format validation — 400 responses (no pipeline interaction needed)
# ---------------------------------------------------------------------------

def test_upload_rejects_unsupported_format(tmp_path: Path):
    s = _settings(tmp_path)
    with TestClient(create_app(s)) as client:
        r = client.post(
            "/api/bundles",
            files={"file": ("firmware.exe", b"binary data", "application/octet-stream")},
        )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "UNSUPPORTED_FORMAT"


def test_upload_rejects_pdf(tmp_path: Path):
    s = _settings(tmp_path)
    with TestClient(create_app(s)) as client:
        r = client.post(
            "/api/bundles",
            files={"file": ("report.pdf", b"%PDF-1.4", "application/pdf")},
        )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "UNSUPPORTED_FORMAT"


def test_upload_rejects_missing_filename(tmp_path: Path):
    s = _settings(tmp_path)
    with TestClient(create_app(s)) as client:
        r = client.post(
            "/api/bundles",
            files={"file": ("", b"data", "application/octet-stream")},
        )
    # FastAPI's multipart parser rejects empty filenames before our handler
    # with a 422; our own guard returns 400 — both mean "rejected".
    assert r.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Accepted formats — 200 responses (pipeline.run mocked)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("filename,content", [
    ("logs.zip", b"PK\x03\x04"),           # zip magic
    ("logs.rar", b"Rar!\x1a\x07\x00"),     # rar magic
    ("system.log", b"2025-01-01 boot\n"),  # plain log
    ("trace.dlt", b"\x44\x4c\x54\x01"),   # DLT magic
    ("notes.txt", b"some notes\n"),        # plain txt
    ("logs.tar.gz", b"\x1f\x8b"),          # gzip magic
    ("bundle.tgz", b"\x1f\x8b"),           # tgz alias
])
def test_upload_accepts_valid_format(tmp_path: Path, filename: str, content: bytes):
    with patch("log_pipeline.ingest.pipeline.IngestPipeline.run", return_value={}):
        s = _settings(tmp_path)
        with TestClient(create_app(s)) as client:
            r = client.post(
                "/api/bundles",
                files={"file": (filename, content, "application/octet-stream")},
            )
    assert r.status_code == 200, f"expected 200 for {filename!r}, got {r.status_code}: {r.text}"
    body = r.json()
    assert body["status"] == "queued"
    assert "bundle_id" in body
