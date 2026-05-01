from __future__ import annotations

from pathlib import Path

from log_pipeline.index.file_index import BucketIndexWriter, RECORD_SIZE, read_bucket_index
from log_pipeline.interfaces import BUCKET_SECONDS


def test_bucket_writer_emits_one_record_per_bucket(tmp_path: Path):
    p = tmp_path / "x.idx"
    # Pick a base aligned to a bucket boundary so the math is easy to read.
    base = (1700000000 // BUCKET_SECONDS) * BUCKET_SECONDS
    with BucketIndexWriter(p) as w:
        # all within bucket B0
        w.append(base + 0, byte_offset=0, line_no=0)
        w.append(base + 30, byte_offset=100, line_no=10)
        w.append(base + 299, byte_offset=200, line_no=20)
        # bucket B1
        w.append(base + 300, byte_offset=300, line_no=30)
        # still B1 (within the same 300s window)
        w.append(base + 599, byte_offset=400, line_no=40)
        # bucket B2
        w.append(base + 600, byte_offset=600, line_no=60)
    records = list(read_bucket_index(p))
    b0 = base // BUCKET_SECONDS
    assert records == [(b0, 0, 0), (b0 + 1, 300, 30), (b0 + 2, 600, 60)]


def test_bucket_writer_atomic_rename(tmp_path: Path):
    p = tmp_path / "y.idx"
    with BucketIndexWriter(p) as w:
        w.append(1700000000, 0, 0)
        # The .partial file exists during writing
        assert (p.with_suffix(p.suffix + ".partial")).exists()
    assert p.exists()
    assert not (p.with_suffix(p.suffix + ".partial")).exists()


def test_bucket_writer_aborts_on_exception(tmp_path: Path):
    p = tmp_path / "z.idx"
    try:
        with BucketIndexWriter(p) as w:
            w.append(1700000000, 0, 0)
            raise RuntimeError("kaboom")
    except RuntimeError:
        pass
    assert not p.exists()
    assert not (p.with_suffix(p.suffix + ".partial")).exists()


def test_bucket_writer_record_size_is_24_bytes(tmp_path: Path):
    assert RECORD_SIZE == 24
    p = tmp_path / "size.idx"
    with BucketIndexWriter(p) as w:
        w.append(1700000000, 0, 0)
        w.append(1700000300, 100, 5)
    assert p.stat().st_size == 2 * 24
