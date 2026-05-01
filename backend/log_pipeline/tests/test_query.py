from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from log_pipeline.index.file_index import BucketIndexWriter
from log_pipeline.interfaces import (
    AlignmentMethod,
    BUCKET_SECONDS,
    ControllerType,
    LogFileMeta,
    MIN_VALID_TS,
)
from log_pipeline.query.range_query import (
    RangeQuery,
    RangeQueryParams,
    estimate_total_lines,
)
from log_pipeline.query.slim_filter import SlimFilter
from log_pipeline.storage.catalog import Catalog


# ---------------- slim filter ----------------


def _slim_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "slim.yaml"
    p.write_text(
        """
slim:
  drop:
    - controller: android
      patterns:
        - 'I/chatty'
        - '^\\s*V/'
    - controller: kernel
      patterns:
        - 'audit:'
  keep_always:
    - '(?i)\\bpanic\\b'
    - '(?i)\\bfatal\\b'
""",
        encoding="utf-8",
    )
    return p


def test_slim_keep_always_overrides_drop(tmp_path: Path):
    sf = SlimFilter.from_yaml(_slim_yaml(tmp_path))
    # 'panic' inside an android line that would otherwise be dropped → kept
    assert sf.keep(ControllerType.ANDROID, "I/chatty: identical lines panic detected")


def test_slim_drop_patterns_per_controller(tmp_path: Path):
    sf = SlimFilter.from_yaml(_slim_yaml(tmp_path))
    assert not sf.keep(ControllerType.ANDROID, "I/chatty: 5 identical lines")
    assert not sf.keep(ControllerType.ANDROID, "  V/foo: verbose")
    # the same `audit:` text is dropped only for kernel, not android
    assert not sf.keep(ControllerType.KERNEL, "audit: type=1400 ...")
    assert sf.keep(ControllerType.ANDROID, "audit: not a kernel rule")


def test_slim_passthrough_default(tmp_path: Path):
    sf = SlimFilter.from_yaml(_slim_yaml(tmp_path))
    assert sf.keep(ControllerType.TBOX, "ordinary log line, no rule applies")


def test_slim_empty_filter_keeps_everything():
    sf = SlimFilter.empty()
    assert sf.keep(ControllerType.ANDROID, "anything")


# ---------------- range query ----------------


def _build_decoded_log(path: Path, base_ts: float, n_lines: int) -> tuple[Path, list[float]]:
    """Write a synthetic Android-style decoded log with lines at base_ts + i*1.0s,
    return its path and the list of raw timestamps."""
    dt = datetime.fromtimestamp(base_ts, tz=timezone.utc)
    year = dt.year
    lines: list[str] = []
    timestamps: list[float] = []
    for i in range(n_lines):
        ts = base_ts + i * 1.0
        d = datetime.fromtimestamp(ts, tz=timezone.utc)
        # MM-DD HH:MM:SS.uuuuuu format expected by android logcat parser
        line = (
            f"{d.month:02d}-{d.day:02d} {d.hour:02d}:{d.minute:02d}:{d.second:02d}."
            f"{d.microsecond:06d}   1   1 W Test: msg-{i}"
        )
        lines.append(line)
        timestamps.append(ts)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path, timestamps


def _make_bundle_with_one_android_file(
    tmp_path: Path,
    catalog_db: Path,
    base_ts: float,
    n_lines: int,
    offset: float = 0.0,
) -> tuple[Catalog, LogFileMeta, list[float]]:
    catalog = Catalog(catalog_db)
    bid = uuid4()
    catalog.create_bundle(bid, "test.zip", 1)
    decoded, timestamps = _build_decoded_log(
        tmp_path / "saicmaxus@2025-01-01_00-00-00.log", base_ts, n_lines
    )

    # build bucket index
    idx_path = tmp_path / f"{uuid4()}.idx"
    with BucketIndexWriter(idx_path) as w:
        # walk the actual byte offsets so the seek logic is realistic
        cur = 0
        for i, ts in enumerate(timestamps):
            w.append(ts, byte_offset=cur, line_no=i)
            cur += len(decoded.read_bytes().splitlines(keepends=True)[i])

    fid = uuid4()
    meta = LogFileMeta(
        file_id=fid,
        bundle_id=bid,
        controller=ControllerType.ANDROID,
        original_name=decoded.name,
        stored_path=str(decoded),
        bundle_relative_path=str(decoded),
        decoded_path=str(decoded),
        size_bytes=decoded.stat().st_size,
        line_count=n_lines,
        raw_ts_min=timestamps[0],
        raw_ts_max=timestamps[-1],
        valid_ts_min=timestamps[0],
        valid_ts_max=timestamps[-1],
        bucket_index_path=str(idx_path),
        clock_offset=offset,
        offset_confidence=1.0,
        offset_method=AlignmentMethod.DIRECT,
    )
    catalog.insert_file_meta(meta)
    catalog.update_file_clock_offset(fid, offset, 1.0, AlignmentMethod.DIRECT.value)
    catalog.update_file_prescan_meta(
        file_id=fid,
        bucket_index_path=str(idx_path),
        line_count=n_lines,
        raw_ts_min=timestamps[0],
        raw_ts_max=timestamps[-1],
        valid_ts_min=timestamps[0],
        valid_ts_max=timestamps[-1],
        unsynced_line_ranges=[],
    )
    return catalog, meta, timestamps


def test_range_query_window_filters_lines(tmp_path: Path, catalog_db: Path):
    base = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp() + 10_000
    cat, meta, ts = _make_bundle_with_one_android_file(tmp_path, catalog_db, base, n_lines=20)
    rq = RangeQuery(cat)
    params = RangeQueryParams(bundle_id=meta.bundle_id, start=ts[5], end=ts[10])
    records = [r for r in rq.stream(params) if not r.get("_meta")]
    # inclusive bounds: lines 5..10
    assert [r["line_no"] for r in records] == [5, 6, 7, 8, 9, 10]
    for r in records:
        assert r["controller"] == "android"
        assert r["aligned_ts"] is not None


def test_range_query_applies_clock_offset(tmp_path: Path, catalog_db: Path):
    base = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp() + 10_000
    cat, meta, ts = _make_bundle_with_one_android_file(
        tmp_path, catalog_db, base, n_lines=10, offset=100.0
    )
    rq = RangeQuery(cat)
    # query in aligned (tbox) time → file ts is base, aligned = base + 100
    aligned_start = ts[3] + 100.0
    aligned_end = ts[5] + 100.0
    params = RangeQueryParams(bundle_id=meta.bundle_id, start=aligned_start, end=aligned_end)
    records = [r for r in rq.stream(params) if not r.get("_meta")]
    assert [r["line_no"] for r in records] == [3, 4, 5]
    for r in records:
        assert r["aligned_ts"] == pytest.approx(r["raw_ts"] + 100.0)


def test_range_query_limit_truncation_marker(tmp_path: Path, catalog_db: Path):
    base = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp() + 10_000
    cat, meta, ts = _make_bundle_with_one_android_file(tmp_path, catalog_db, base, n_lines=50)
    rq = RangeQuery(cat)
    params = RangeQueryParams(
        bundle_id=meta.bundle_id, start=ts[0], end=ts[-1], limit=10
    )
    records = list(rq.stream(params))
    meta_record = records[-1]
    assert meta_record.get("_meta") is True
    data_records = records[:-1]
    assert len(data_records) == 10
    assert meta_record["truncated"] is True


def test_range_query_slim_mode_drops_filtered_lines(tmp_path: Path, catalog_db: Path):
    base = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp() + 10_000
    cat, meta, ts = _make_bundle_with_one_android_file(tmp_path, catalog_db, base, n_lines=5)
    # tweak the file to have one panic line
    decoded = Path(meta.stored_path)
    text = decoded.read_text(encoding="utf-8")
    lines = text.splitlines()
    lines[2] = lines[2].replace("Test: msg-2", "Test: panic detected here")
    lines[3] = lines[3].replace("Test: msg-3", "Test: I/chatty: identical lines")
    decoded.write_text("\n".join(lines) + "\n", encoding="utf-8")

    sf = SlimFilter.from_yaml(_slim_yaml(tmp_path))
    rq = RangeQuery(cat, sf)
    params = RangeQueryParams(
        bundle_id=meta.bundle_id, start=ts[0], end=ts[-1], format="slim"
    )
    records = [r for r in rq.stream(params) if not r.get("_meta")]
    texts = [r["line"] for r in records]
    assert any("panic" in t for t in texts)
    assert not any("I/chatty" in t for t in texts)


def test_range_query_filters_by_controller(tmp_path: Path, catalog_db: Path):
    base = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp() + 10_000
    cat, meta, ts = _make_bundle_with_one_android_file(tmp_path, catalog_db, base, n_lines=5)
    rq = RangeQuery(cat)
    params = RangeQueryParams(
        bundle_id=meta.bundle_id, start=ts[0], end=ts[-1],
        controllers=[ControllerType.MCU],  # no MCU file exists
    )
    records = [r for r in rq.stream(params) if not r.get("_meta")]
    assert records == []


def test_estimate_total_lines_overlap(tmp_path: Path, catalog_db: Path):
    base = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp() + 10_000
    cat, meta, ts = _make_bundle_with_one_android_file(tmp_path, catalog_db, base, n_lines=42)
    params = RangeQueryParams(bundle_id=meta.bundle_id, start=ts[0], end=ts[-1])
    assert estimate_total_lines(cat, params) == 42

    # no-overlap window
    out_of_range = RangeQueryParams(
        bundle_id=meta.bundle_id, start=ts[-1] + 10000, end=ts[-1] + 11000
    )
    assert estimate_total_lines(cat, out_of_range) == 0


# ---------------- HTTP endpoints ----------------


def test_http_logs_endpoint_streams_ndjson(tmp_path: Path):
    from fastapi.testclient import TestClient
    from log_pipeline.api.http import create_app
    from log_pipeline.config import Settings
    from log_pipeline.ingest.pipeline import IngestPipeline

    base = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp() + 10_000
    db = tmp_path / "catalog.db"
    cat, meta, ts = _make_bundle_with_one_android_file(tmp_path, db, base, n_lines=8)

    settings = Settings(
        store_root=tmp_path / "store",
        upload_root=tmp_path / "uploads",
        work_root=tmp_path / "work",
        index_root=tmp_path / "indexes",
        catalog_db=db,
        classifier_yaml=Path("config/controllers.yaml"),
        event_rules_yaml=Path("config/event_rules.yaml"),
        anchor_rules_yaml=Path("config/anchor_rules.yaml"),
        slim_rules_yaml=Path("config/slim_rules.yaml"),
    )
    app = create_app(settings)

    with TestClient(app) as client:
        r = client.get(
            f"/api/bundles/{meta.bundle_id}/logs",
            params={"start": ts[2], "end": ts[6]},
        )
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/x-ndjson")
        assert r.headers["x-truncated"] in {"true", "false"}
        body = r.content.decode("utf-8").strip().split("\n")
        records = [json.loads(line) for line in body]
        data = [r for r in records if not r.get("_meta")]
        meta_marker = records[-1]
        assert [r["line_no"] for r in data] == [2, 3, 4, 5, 6]
        assert meta_marker["_meta"] is True
        assert meta_marker["truncated"] is False
        assert meta_marker["lines_emitted"] == 5


def test_http_logs_invalid_uuid_returns_400(tmp_path: Path):
    from fastapi.testclient import TestClient
    from log_pipeline.api.http import create_app
    from log_pipeline.config import Settings

    db = tmp_path / "catalog.db"
    Catalog(db)  # init schema
    settings = Settings(
        store_root=tmp_path / "store",
        upload_root=tmp_path / "uploads",
        work_root=tmp_path / "work",
        index_root=tmp_path / "indexes",
        catalog_db=db,
        classifier_yaml=Path("config/controllers.yaml"),
        event_rules_yaml=Path("config/event_rules.yaml"),
        anchor_rules_yaml=Path("config/anchor_rules.yaml"),
        slim_rules_yaml=Path("config/slim_rules.yaml"),
    )
    app = create_app(settings)
    with TestClient(app) as client:
        r = client.get(
            "/api/bundles/not-a-uuid/logs", params={"start": 0, "end": 1}
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_BUNDLE_ID"


def test_http_events_endpoint_returns_filtered_events(tmp_path: Path):
    from fastapi.testclient import TestClient
    from log_pipeline.api.http import create_app
    from log_pipeline.config import Settings
    from log_pipeline.interfaces import ImportantEvent
    from log_pipeline.storage.eventdb import EventDB

    db = tmp_path / "catalog.db"
    cat = Catalog(db)
    bid = uuid4()
    fid = uuid4()
    cat.create_bundle(bid, "x.zip", 1)
    eventdb = EventDB(db)
    eventdb.insert_events_batch([
        ImportantEvent(
            event_id=uuid4(), bundle_id=bid, file_id=fid,
            controller=ControllerType.MCU, event_type="gear_shift",
            raw_timestamp=1700000010.0, aligned_timestamp=None, alignment_quality=0.0,
            line_no=1, raw_line="GEAR -> D", extracted_fields={"gear": "D"},
        ),
        ImportantEvent(
            event_id=uuid4(), bundle_id=bid, file_id=fid,
            controller=ControllerType.ANDROID, event_type="system_reboot",
            raw_timestamp=1700000020.0, aligned_timestamp=None, alignment_quality=0.0,
            line_no=2, raw_line="reboot now", extracted_fields={},
        ),
    ])
    settings = Settings(
        store_root=tmp_path / "store",
        upload_root=tmp_path / "uploads",
        work_root=tmp_path / "work",
        index_root=tmp_path / "indexes",
        catalog_db=db,
        classifier_yaml=Path("config/controllers.yaml"),
        event_rules_yaml=Path("config/event_rules.yaml"),
        anchor_rules_yaml=Path("config/anchor_rules.yaml"),
        slim_rules_yaml=Path("config/slim_rules.yaml"),
    )
    app = create_app(settings)
    with TestClient(app) as client:
        r = client.get(f"/api/bundles/{bid}/events", params={"types": "gear_shift"})
        assert r.status_code == 200
        events = r.json()
        assert len(events) == 1
        assert events[0]["event_type"] == "gear_shift"
        # JSON-serialised extracted_fields
        assert "gear" in events[0]["extracted_fields_json"]
