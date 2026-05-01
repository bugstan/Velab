from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from log_pipeline.decoders.base import default_registry
from log_pipeline.interfaces import (
    INVALID_TS_SENTINEL_2020_END,
    MIN_VALID_TS,
    AlignmentMethod,
    BootSegment,
    ControllerType,
    LogFileMeta,
)
from log_pipeline.prescan.prescanner import (
    Prescanner,
    iter_dlt_decoded_log,
    parse_dlt_decoded_timestamp,
)
from log_pipeline.prescan.rule_engine import RuleEngine


def _meta(stored_path: str, decoded_path: str, controller=ControllerType.ANDROID) -> LogFileMeta:
    return LogFileMeta(
        file_id=uuid4(),
        bundle_id=uuid4(),
        controller=controller,
        original_name=Path(stored_path).name,
        stored_path=stored_path,
        bundle_relative_path=stored_path,
        decoded_path=decoded_path,
        offset_method=AlignmentMethod.NONE,
    )


def test_parse_dlt_decoded_timestamp():
    ts = parse_dlt_decoded_timestamp("2025-09-01T14:38:13.266447 TBOX NTSP NTSP payload")
    assert ts is not None
    # Recompute expected
    from datetime import datetime, timezone

    expected = datetime(2025, 9, 1, 14, 38, 13, tzinfo=timezone.utc).timestamp() + 0.266447
    assert abs(ts - expected) < 1e-3


def test_iter_dlt_decoded_log(tmp_path: Path):
    p = tmp_path / "x.decoded.log"
    p.write_text(
        "2025-09-01T14:38:13.000000 TBOX A B msg-one\n"
        "2025-09-01T14:38:14.500000 TBOX A B msg-two\n"
        "garbage line without timestamp\n",
        encoding="utf-8",
    )
    lines = list(iter_dlt_decoded_log(p))
    assert len(lines) == 3
    assert lines[0].raw_timestamp is not None
    assert lines[2].raw_timestamp is None


def test_prescanner_text_file_collects_events(tmp_path: Path, classifier_yaml: Path):
    p = tmp_path / "saicmaxus@2025-09-12_10-00-00.000.log"
    p.write_text(
        "09-12 10:00:00.000000   1   1 W Tag: boot completed at startup\n"
        "09-12 10:00:01.000000   1   1 I Tag: nothing here\n"
        "09-12 10:00:02.000000   1   1 E Tag: system reboot reason=watchdog now\n",
        encoding="utf-8",
    )
    rules = RuleEngine.from_yaml_files(
        Path("config/event_rules.yaml"), Path("config/anchor_rules.yaml")
    )
    pre = Prescanner(default_registry(), rules)
    meta = _meta(str(p), str(p), controller=ControllerType.ANDROID)
    res = pre.run_file(meta, tmp_path)
    assert res is not None
    assert res.line_count == 3
    types = {ev.event_type for ev in res.events}
    assert {"system_boot", "system_reboot"}.issubset(types)
    # at least one fired event has the watchdog reason field
    reboots = [ev for ev in res.events if ev.event_type == "system_reboot"]
    assert any(ev.extracted_fields.get("reason") == "watchdog" for ev in reboots)
    # bucket index file written
    assert res.bucket_index_path is not None
    assert Path(res.bucket_index_path).exists()


def test_prescanner_marks_unsynced_ranges(tmp_path: Path):
    p = tmp_path / "kernel@2025-09-11_07-13-33.log"
    # Construct with boot-time fake "01-01" prefix lines, then synced "09-11" lines
    fake_year = "01-01 10:00:00.000000   1   1 I Tag: msg\n"
    real_line = "09-11 12:00:00.000000   1   1 I Tag: msg\n"
    # Need year 1970 to dip below MIN_VALID_TS — KernelLogcatDecoder uses filename year (2025).
    # For this test: write a dmesg file (relative time 0..) which is well below MIN_VALID_TS.
    p2 = tmp_path / "176_2025-09-10_14-44-01.log"
    p2.write_text(
        "[    0.000000] Booting Linux\n"
        "[    0.500000] random init\n"
        "[    1.000000] later\n",
        encoding="utf-8",
    )
    rules = RuleEngine.from_yaml_files(
        Path("config/event_rules.yaml"), Path("config/anchor_rules.yaml")
    )
    pre = Prescanner(default_registry(), rules)
    meta = _meta(str(p2), str(p2), controller=ControllerType.KERNEL)
    res = pre.run_file(meta, tmp_path)
    assert res is not None
    # all lines have ts < MIN_VALID_TS so the entire file is one unsynced range
    assert res.unsynced_line_ranges == [(0, 2)]
    assert res.bucket_record_count == 0


def test_prescanner_dlt_replay_uses_decoded_text(tmp_path: Path):
    decoded = tmp_path / "trace.decoded.log"
    decoded.write_text(
        "2025-09-01T14:38:13.000000 TBOX MNT MNT FOTA download start now\n"
        "2025-09-01T14:38:14.000000 TBOX MNT MNT info: rtc set hw ok\n",
        encoding="utf-8",
    )
    stored = tmp_path / "trace.dlt"
    stored.write_bytes(b"DLT\x01" + b"\x00" * 20)
    rules = RuleEngine.from_yaml_files(
        Path("config/event_rules.yaml"), Path("config/anchor_rules.yaml")
    )
    pre = Prescanner(default_registry(), rules)
    meta = _meta(str(stored), str(decoded), controller=ControllerType.TBOX)
    res = pre.run_file(meta, tmp_path)
    assert res is not None
    assert res.line_count == 2
    types = {ev.event_type for ev in res.events}
    assert "fota_download_start" in types
    anchors = {a.anchor_type for a in res.anchors}
    assert "tbox_clock_sync" in anchors


def test_prescanner_prealigned_sentinel_day_not_counted_as_valid(tmp_path: Path):
    p = tmp_path / "176_2020-01-01_00-00-00.log"
    p.write_text(
        "[    0.000000] Booting Linux\n"
        "[    1.000000] random init\n",
        encoding="utf-8",
    )
    rules = RuleEngine.from_yaml_files(
        Path("config/event_rules.yaml"), Path("config/anchor_rules.yaml")
    )
    pre = Prescanner(default_registry(), rules)
    meta = LogFileMeta(
        file_id=uuid4(),
        bundle_id=uuid4(),
        controller=ControllerType.KERNEL,
        original_name=p.name,
        stored_path=str(p),
        bundle_relative_path=str(p),
        decoded_path=str(p),
        offset_method=AlignmentMethod.FILENAME_ANCHOR,
        clock_offset=MIN_VALID_TS,
    )
    res = pre.run_file(meta, tmp_path)
    assert res is not None
    assert res.valid_ts_min is None
    assert res.valid_ts_max is None
    assert res.unsynced_line_ranges == [(0, 1)]
    assert res.bucket_record_count == 0


def test_prescanner_segmented_sentinel_day_not_counted_as_valid(tmp_path: Path):
    p = tmp_path / "mcu_1.log"
    p.write_text(
        "&0 INF@SYS : hello\n"
        "&1000 INF@SYS : world\n",
        encoding="utf-8",
    )
    rules = RuleEngine.from_yaml_files(
        Path("config/event_rules.yaml"), Path("config/anchor_rules.yaml")
    )
    pre = Prescanner(default_registry(), rules)
    meta = LogFileMeta(
        file_id=uuid4(),
        bundle_id=uuid4(),
        controller=ControllerType.MCU,
        original_name=p.name,
        stored_path=str(p),
        bundle_relative_path=str(p),
        decoded_path=str(p),
        offset_method=AlignmentMethod.SEGMENTED,
        segments=(
            BootSegment(
                seq_no=0,
                line_start=0,
                line_end=2,
                byte_start=0,
                byte_end=p.stat().st_size,
                raw_ts_min=0.0,
                raw_ts_max=1.0,
                clock_offset=MIN_VALID_TS + 60.0,
                offset_confidence=0.95,
            ),
        ),
    )
    res = pre.run_file(meta, tmp_path)
    assert res is not None
    assert res.valid_ts_min is None
    assert res.valid_ts_max is None
    assert res.unsynced_line_ranges == [(0, 1)]
    assert res.bucket_index_path is None
    assert INVALID_TS_SENTINEL_2020_END > MIN_VALID_TS
