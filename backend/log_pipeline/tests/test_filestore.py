from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from log_pipeline.interfaces import ControllerType
from log_pipeline.storage.filestore import FileStore, _sanitize_basename


def test_sanitize_basename_drops_path_separators():
    assert _sanitize_basename("a/b/c.log") == "c.log"
    assert _sanitize_basename("a\\b\\c.log") == "c.log"


def test_sanitize_basename_replaces_control_chars():
    assert _sanitize_basename("foo\x00bar.log") == "foo_bar.log"


def test_sanitize_basename_truncates_overlong():
    long = "x" * 300 + ".log"
    out = _sanitize_basename(long)
    assert len(out) <= 200
    assert out.endswith(".log")


def test_filestore_no_overwrite_for_same_basename(store_root: Path, tmp_path: Path):
    fs = FileStore(store_root)
    bundle_id = uuid4()
    fs.init_bundle(bundle_id)

    src1 = tmp_path / "src1.bin"
    src1.write_bytes(b"AAA")
    meta1 = fs.store_file(bundle_id, ControllerType.ANDROID, "subdir1/main.log", src1)

    src2 = tmp_path / "src2.bin"
    src2.write_bytes(b"BBB")
    meta2 = fs.store_file(bundle_id, ControllerType.ANDROID, "subdir2/main.log", src2)

    assert meta1.file_id != meta2.file_id
    assert Path(meta1.stored_path).exists()
    assert Path(meta2.stored_path).exists()
    assert Path(meta1.stored_path).read_bytes() == b"AAA"
    assert Path(meta2.stored_path).read_bytes() == b"BBB"
    assert Path(meta1.stored_path).name.endswith("__main.log")
    assert Path(meta2.stored_path).name.endswith("__main.log")
    assert meta1.bundle_relative_path == "subdir1/main.log"
    assert meta2.bundle_relative_path == "subdir2/main.log"


def test_filestore_processing_log_records_stages(store_root: Path):
    fs = FileStore(store_root)
    bundle_id = uuid4()
    fs.init_bundle(bundle_id)
    with fs.processing_log(bundle_id, "extract"):
        fs.append_processing_log(bundle_id, "did some work")

    text = (fs.bundle_dir(bundle_id) / "_processing.log").read_text(encoding="utf-8")
    assert "stage=extract status=start" in text
    assert "did some work" in text
    assert "stage=extract status=ok" in text


def test_filestore_processing_log_captures_error(store_root: Path):
    fs = FileStore(store_root)
    bundle_id = uuid4()
    fs.init_bundle(bundle_id)
    try:
        with fs.processing_log(bundle_id, "boom"):
            raise RuntimeError("kaboom")
    except RuntimeError:
        pass
    text = (fs.bundle_dir(bundle_id) / "_processing.log").read_text(encoding="utf-8")
    assert "stage=boom status=error" in text
    assert "kaboom" in text
