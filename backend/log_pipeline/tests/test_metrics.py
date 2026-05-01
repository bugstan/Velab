from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from log_pipeline.api.http import create_app
from log_pipeline.config import Settings
from log_pipeline.interfaces import (
    AlignmentMethod,
    BundleStatus,
    ControllerType,
    ImportantEvent,
    LogFileMeta,
)
from log_pipeline.storage.catalog import Catalog
from log_pipeline.storage.eventdb import EventDB


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


def _seed(catalog: Catalog, eventdb: EventDB) -> None:
    bid = uuid4()
    catalog.create_bundle(bid, "demo.zip", 100)
    catalog.update_bundle_status(bid, BundleStatus.DONE, progress=1.0)
    fid = uuid4()
    catalog.insert_file_meta(
        LogFileMeta(
            file_id=fid,
            bundle_id=bid,
            controller=ControllerType.ANDROID,
            original_name="x.log",
            stored_path="/tmp/x.log",
            bundle_relative_path="a/x.log",
            size_bytes=10,
            clock_offset=8.83,
            offset_confidence=0.54,
            offset_method=AlignmentMethod.DIRECT,
        )
    )
    catalog.update_file_clock_offset(fid, 8.83, 0.54, AlignmentMethod.DIRECT.value)
    eventdb.insert_events_batch([
        ImportantEvent(
            event_id=uuid4(), bundle_id=bid, file_id=fid,
            controller=ControllerType.ANDROID, event_type="system_reboot",
            raw_timestamp=1700000000.0, aligned_timestamp=None, alignment_quality=0.0,
            line_no=1, raw_line="reboot", extracted_fields={},
        ),
        ImportantEvent(
            event_id=uuid4(), bundle_id=bid, file_id=fid,
            controller=ControllerType.ANDROID, event_type="system_boot",
            raw_timestamp=1700000010.0, aligned_timestamp=None, alignment_quality=0.0,
            line_no=2, raw_line="boot completed", extracted_fields={},
        ),
    ])


def test_metrics_endpoint_exposes_required_series(tmp_path: Path):
    s = _settings(tmp_path)
    catalog = Catalog(s.catalog_db)
    eventdb = EventDB(s.catalog_db)
    _seed(catalog, eventdb)

    app = create_app(s)
    with TestClient(app) as client:
        r = client.get("/metrics")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/plain")
        body = r.text
        # Required Prometheus series per CLAUDE.md §10
        assert "log_pipeline_bundles_total" in body
        assert "log_pipeline_files_total" in body
        assert "log_pipeline_events_extracted_total" in body
        assert "log_pipeline_alignment_offset_seconds" in body
        assert "log_pipeline_alignment_confidence" in body
        # specific samples
        assert 'log_pipeline_bundles_total{status="done"} 1' in body
        assert 'log_pipeline_files_total{controller="android"} 1' in body
        assert 'log_pipeline_events_extracted_total{event_type="system_reboot"} 1' in body
        assert 'log_pipeline_events_extracted_total{event_type="system_boot"} 1' in body
        assert 'log_pipeline_alignment_offset_seconds{controller="android"} 8.83' in body


def test_metrics_endpoint_handles_empty_db(tmp_path: Path):
    s = _settings(tmp_path)
    Catalog(s.catalog_db)  # init schema
    EventDB(s.catalog_db)
    app = create_app(s)
    with TestClient(app) as client:
        r = client.get("/metrics")
        assert r.status_code == 200
        # Should still emit HELP/TYPE comments without any sample rows
        assert "# HELP log_pipeline_bundles_total" in r.text
        assert "# TYPE log_pipeline_files_total" in r.text
