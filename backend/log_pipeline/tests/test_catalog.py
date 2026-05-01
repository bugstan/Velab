from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from log_pipeline.interfaces import (
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
