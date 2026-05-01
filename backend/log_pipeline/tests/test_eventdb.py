from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from log_pipeline.interfaces import (
    AnchorCandidate,
    ControllerType,
    ImportantEvent,
    RAW_LINE_TRUNCATE_BYTES,
)
from log_pipeline.storage.eventdb import EventDB


def _ev(
    bundle_id, file_id, controller=ControllerType.ANDROID, event_type="system_reboot",
    raw_ts=1700000000.0, line_no=42, raw_line="boot reason=watchdog", fields=None,
):
    return ImportantEvent(
        event_id=uuid4(),
        bundle_id=bundle_id,
        file_id=file_id,
        controller=controller,
        event_type=event_type,
        raw_timestamp=raw_ts,
        aligned_timestamp=None,
        alignment_quality=0.0,
        line_no=line_no,
        raw_line=raw_line,
        extracted_fields=fields or {},
    )


def test_events_batch_insert_and_count(tmp_path: Path):
    db = EventDB(tmp_path / "db.sqlite")
    bid = uuid4()
    fid = uuid4()
    n = db.insert_events_batch([
        _ev(bid, fid, event_type="system_reboot"),
        _ev(bid, fid, event_type="system_reboot"),
        _ev(bid, fid, event_type="fota_install_start", raw_ts=1700000100.0),
    ])
    assert n == 3
    assert db.count_events_by_type(bid) == {"system_reboot": 2, "fota_install_start": 1}


def test_events_filter_by_type_controller_time(tmp_path: Path):
    db = EventDB(tmp_path / "db.sqlite")
    bid = uuid4()
    fid = uuid4()
    db.insert_events_batch([
        _ev(bid, fid, ControllerType.ANDROID, "system_reboot", 100.0),
        _ev(bid, fid, ControllerType.MCU, "system_reboot", 200.0),
        _ev(bid, fid, ControllerType.MCU, "gear_shift", 300.0,
            fields={"gear": "D"}, raw_line="GEAR -> D"),
    ])
    only_mcu = db.list_events(bid, controllers=[ControllerType.MCU])
    assert len(only_mcu) == 2
    only_reboot = db.list_events(bid, event_types=["system_reboot"])
    assert {r["controller"] for r in only_reboot} == {"android", "mcu"}
    in_window = db.list_events(bid, start=150, end=250)
    assert len(in_window) == 1
    assert in_window[0]["controller"] == "mcu"
    # extracted fields persisted as JSON
    [gs] = db.list_events(bid, event_types=["gear_shift"])
    assert '"gear": "D"' in gs["extracted_fields_json"]


def test_events_truncate_long_raw_line(tmp_path: Path):
    db = EventDB(tmp_path / "db.sqlite")
    bid = uuid4()
    fid = uuid4()
    long_line = "x" * (RAW_LINE_TRUNCATE_BYTES + 500)
    db.insert_events_batch([_ev(bid, fid, raw_line=long_line)])
    [row] = db.list_events(bid)
    assert len(row["raw_line"].encode("utf-8")) <= RAW_LINE_TRUNCATE_BYTES


def test_anchors_batch_insert_and_count(tmp_path: Path):
    db = EventDB(tmp_path / "db.sqlite")
    bid = uuid4()
    fid = uuid4()
    db.insert_anchors_batch(bid, fid, [
        AnchorCandidate(
            anchor_type="tbox_clock_sync",
            controller=ControllerType.TBOX,
            raw_timestamp=1700000000.0,
            line_no=10,
            confidence=0.98,
            fields={},
        ),
        AnchorCandidate(
            anchor_type="system_boot",
            controller=ControllerType.ANDROID,
            raw_timestamp=1700000010.0,
            line_no=5,
            confidence=0.9,
            fields={},
        ),
    ])
    counts = db.count_anchors_by_type(bid)
    assert counts == {"tbox_clock_sync": 1, "system_boot": 1}
    rows = db.list_anchors(bid)
    assert len(rows) == 2


def test_clear_for_bundle_resets_only_that_bundle(tmp_path: Path):
    db = EventDB(tmp_path / "db.sqlite")
    bid_a, bid_b = uuid4(), uuid4()
    fid = uuid4()
    db.insert_events_batch([_ev(bid_a, fid), _ev(bid_b, fid)])
    db.clear_for_bundle(bid_a)
    assert db.count_events_by_type(bid_a) == {}
    assert db.count_events_by_type(bid_b) == {"system_reboot": 1}
