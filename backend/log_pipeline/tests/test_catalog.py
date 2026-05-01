from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from log_pipeline.interfaces import (
    INVALID_TS_SENTINEL_2020_END,
    MIN_VALID_TS,
    AlignmentMethod,
    BundleStatus,
    ControllerType,
    LogFileMeta,
)
from log_pipeline.storage.catalog import Catalog


def test_catalog_bundle_lifecycle(catalog_db: Path):
    cat = Catalog(catalog_db)
    bid = uuid4()
    cat.create_bundle(bid, archive_filename="x.zip", archive_size_bytes=123)

    b = cat.get_bundle(bid)
    assert b is not None
    assert b["status"] == BundleStatus.QUEUED.value
    assert b["archive_filename"] == "x.zip"
    assert b["archive_size_bytes"] == 123

    cat.update_bundle_status(bid, BundleStatus.EXTRACTING, progress=0.4)
    b = cat.get_bundle(bid)
    assert b["status"] == BundleStatus.EXTRACTING.value
    assert b["progress"] == 0.4

    cat.update_bundle_status(bid, BundleStatus.FAILED, error="boom")
    b = cat.get_bundle(bid)
    assert b["status"] == BundleStatus.FAILED.value
    assert b["error"] == "boom"


def test_catalog_insert_and_list_files(catalog_db: Path):
    cat = Catalog(catalog_db)
    bid = uuid4()
    cat.create_bundle(bid, "x.zip", 1)

    metas = []
    for ctrl, name in [
        (ControllerType.ANDROID, "main.log"),
        (ControllerType.ANDROID, "main.log.1"),
        (ControllerType.TBOX, "trace.dlt"),
    ]:
        m = LogFileMeta(
            file_id=uuid4(),
            bundle_id=bid,
            controller=ctrl,
            original_name=name,
            stored_path=f"/tmp/{name}",
            bundle_relative_path=f"path/{name}",
            size_bytes=42,
        )
        cat.insert_file_meta(m)
        metas.append(m)

    listed = cat.list_files_by_bundle(bid)
    assert len(listed) == 3
    assert {m.original_name for m in listed} == {m.original_name for m in metas}

    counts = cat.count_by_controller(bid)
    assert counts == {"android": 2, "tbox": 1}


def test_catalog_unsynced_ranges_roundtrip(catalog_db: Path):
    cat = Catalog(catalog_db)
    bid = uuid4()
    cat.create_bundle(bid, "x.zip", 1)
    m = LogFileMeta(
        file_id=uuid4(),
        bundle_id=bid,
        controller=ControllerType.MCU,
        original_name="x.log",
        stored_path="/tmp/x.log",
        bundle_relative_path="x.log",
        size_bytes=10,
        unsynced_line_ranges=((0, 99), (200, 300)),
        offset_method=AlignmentMethod.TWO_HOP,
        offset_confidence=0.7,
    )
    cat.insert_file_meta(m)
    [back] = cat.list_files_by_bundle(bid)
    assert back.unsynced_line_ranges == ((0, 99), (200, 300))
    assert back.offset_method == AlignmentMethod.TWO_HOP
    assert back.offset_confidence == 0.7


def test_valid_time_range_by_controller_uses_aligned_semantics(catalog_db: Path):
    cat = Catalog(catalog_db)
    bid = uuid4()
    cat.create_bundle(bid, "x.zip", 1)

    sentinel = LogFileMeta(
        file_id=uuid4(),
        bundle_id=bid,
        controller=ControllerType.KERNEL,
        original_name="boot_2020.log",
        stored_path="/tmp/boot_2020.log",
        bundle_relative_path="kernel_logs/1_2020-01-01_00-00-00.log",
        valid_ts_min=0.0,
        valid_ts_max=10.0,
        clock_offset=MIN_VALID_TS,
        offset_method=AlignmentMethod.FILENAME_ANCHOR,
    )
    valid = LogFileMeta(
        file_id=uuid4(),
        bundle_id=bid,
        controller=ControllerType.KERNEL,
        original_name="boot_2026.log",
        stored_path="/tmp/boot_2026.log",
        bundle_relative_path="kernel_logs/2_2026-01-01_00-00-00.log",
        valid_ts_min=100.0,
        valid_ts_max=130.0,
        clock_offset=MIN_VALID_TS + 2 * 86400.0,
        offset_method=AlignmentMethod.FILENAME_ANCHOR,
    )
    cat.insert_file_meta(sentinel)
    cat.insert_file_meta(valid)

    out = cat.valid_time_range_by_controller(bid)
    assert out["kernel"]["start"] == MIN_VALID_TS + 2 * 86400.0 + 100.0
    assert out["kernel"]["end"] == MIN_VALID_TS + 2 * 86400.0 + 130.0


def test_valid_time_range_by_controller_filters_segmented_sentinel_day(catalog_db: Path):
    cat = Catalog(catalog_db)
    bid = uuid4()
    cat.create_bundle(bid, "x.zip", 1)

    mcu_seg_sentinel = LogFileMeta(
        file_id=uuid4(),
        bundle_id=bid,
        controller=ControllerType.MCU,
        original_name="mcu_sentinel.log",
        stored_path="/tmp/mcu_sentinel.log",
        bundle_relative_path="mcu/mcu_sentinel.log",
        valid_ts_min=MIN_VALID_TS + 60.0,
        valid_ts_max=MIN_VALID_TS + 120.0,
        offset_method=AlignmentMethod.SEGMENTED,
    )
    mcu_seg_valid = LogFileMeta(
        file_id=uuid4(),
        bundle_id=bid,
        controller=ControllerType.MCU,
        original_name="mcu_valid.log",
        stored_path="/tmp/mcu_valid.log",
        bundle_relative_path="mcu/mcu_valid.log",
        valid_ts_min=INVALID_TS_SENTINEL_2020_END + 10.0,
        valid_ts_max=INVALID_TS_SENTINEL_2020_END + 30.0,
        offset_method=AlignmentMethod.SEGMENTED,
    )
    cat.insert_file_meta(mcu_seg_sentinel)
    cat.insert_file_meta(mcu_seg_valid)

    out = cat.valid_time_range_by_controller(bid)
    assert out["mcu"]["start"] == INVALID_TS_SENTINEL_2020_END + 10.0
    assert out["mcu"]["end"] == INVALID_TS_SENTINEL_2020_END + 30.0
