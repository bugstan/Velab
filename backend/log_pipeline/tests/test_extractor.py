from __future__ import annotations

import struct
import zipfile
import zlib
from pathlib import Path

from log_pipeline.ingest.extractor import Extractor, _fix_zip_name


def test_fix_zip_name_decodes_gbk_when_utf8_flag_unset():
    raw = "中文.log".encode("gbk").decode("cp437")
    assert _fix_zip_name(raw, flag_bits=0) == "中文.log"


def test_fix_zip_name_passthrough_when_utf8_flag_set():
    assert _fix_zip_name("中文.log", flag_bits=0x800) == "中文.log"


def _make_zip(path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            info = zipfile.ZipInfo(name)
            info.flag_bits |= 0x800
            zf.writestr(info, data)


def _make_legacy_gbk_zip(path: Path, entries: dict[str, bytes]) -> None:
    """Hand-roll a zip with GBK-encoded filenames and the UTF-8 flag CLEARED.

    Python's zipfile auto-sets the 0x800 flag for non-ASCII names, so we have
    to emit local headers, file data, and central directory bytes ourselves to
    reproduce the legacy-encoding case seen in the real sample bundle.
    """
    local_blocks: list[bytes] = []
    central_blocks: list[bytes] = []
    file_offsets: list[int] = []
    cursor = 0

    for name, data in entries.items():
        name_bytes = name.encode("gbk")
        crc = zlib.crc32(data) & 0xFFFFFFFF
        size = len(data)
        # Local file header (PK\x03\x04, 30 bytes fixed + name + extra)
        local = (
            b"PK\x03\x04"
            + struct.pack(
                "<HHHHHIIIHH",
                20,    # version needed
                0,     # flags (UTF-8 bit cleared)
                0,     # method = stored
                0,     # mod time
                0,     # mod date
                crc,
                size,  # compressed size
                size,  # uncompressed size
                len(name_bytes),
                0,     # extra length
            )
            + name_bytes
        )
        file_offsets.append(cursor)
        local_blocks.append(local)
        local_blocks.append(data)
        cursor += len(local) + len(data)

    # Central directory (PK\x01\x02, 46 bytes fixed + name + extra + comment)
    for (name, data), offset in zip(entries.items(), file_offsets):
        name_bytes = name.encode("gbk")
        crc = zlib.crc32(data) & 0xFFFFFFFF
        size = len(data)
        cd = (
            b"PK\x01\x02"
            + struct.pack(
                "<HHHHHHIIIHHHHHII",
                20,    # version made by
                20,    # version needed
                0,     # flags
                0,     # method
                0,     # mod time
                0,     # mod date
                crc,
                size,  # compressed size
                size,  # uncompressed size
                len(name_bytes),
                0,     # extra length
                0,     # comment length
                0,     # disk number start
                0,     # internal attrs
                0,     # external attrs
                offset,
            )
            + name_bytes
        )
        central_blocks.append(cd)

    cd_blob = b"".join(central_blocks)
    cd_offset = cursor
    end = b"PK\x05\x06" + struct.pack(
        "<HHHHIIH",
        0,                    # disk number
        0,                    # disk with central dir
        len(entries),         # entries on this disk
        len(entries),         # total entries
        len(cd_blob),
        cd_offset,
        0,                    # comment length
    )
    path.write_bytes(b"".join(local_blocks) + cd_blob + end)


def test_extractor_basic(tmp_path: Path, work_root: Path):
    archive = tmp_path / "a.zip"
    _make_zip(archive, {"a/foo.log": b"hello", "a/bar.log": b"world"})
    files = list(Extractor(work_root).extract(archive))
    rels = sorted(f.relative_path for f in files)
    assert rels == ["a/bar.log", "a/foo.log"]
    contents = {f.relative_path: f.temp_path.read_bytes() for f in files}
    assert contents == {"a/foo.log": b"hello", "a/bar.log": b"world"}


def test_extractor_gbk_filename_fix(tmp_path: Path, work_root: Path):
    archive = tmp_path / "gbk.zip"
    _make_legacy_gbk_zip(
        archive,
        {"日志/娱乐系统日志/android/foo.log": b"x"},
    )
    # sanity-check our hand-rolled zip is parseable
    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()
        assert len(infos) == 1
        # zipfile decoded the GBK bytes as cp437 (mojibake) because UTF-8 flag is off
        assert infos[0].flag_bits & 0x800 == 0

    files = list(Extractor(work_root).extract(archive))
    assert len(files) == 1
    assert files[0].relative_path == "日志/娱乐系统日志/android/foo.log"
    assert files[0].temp_path.read_bytes() == b"x"


def test_extractor_skips_ds_store(tmp_path: Path, work_root: Path):
    archive = tmp_path / "ds.zip"
    _make_zip(
        archive,
        {
            "x/.DS_Store": b"junk",
            "__MACOSX/x/._foo": b"junk",
            "x/keep.log": b"keep",
        },
    )
    rels = sorted(f.relative_path for f in Extractor(work_root).extract(archive))
    assert rels == ["x/keep.log"]


def test_extractor_recurses_into_nested_zip(tmp_path: Path, work_root: Path):
    inner = tmp_path / "inner.zip"
    _make_zip(inner, {"deep/a.log": b"AAA", "deep/b.log": b"BBB"})
    outer = tmp_path / "outer.zip"
    _make_zip(outer, {"top/wrap.zip": inner.read_bytes(), "top/note.txt": b"hi"})
    files = list(Extractor(work_root).extract(outer))
    rels = sorted(f.relative_path for f in files)
    assert rels == [
        "top/note.txt",
        "top/wrap.zip/deep/a.log",
        "top/wrap.zip/deep/b.log",
    ]
    by_rel = {f.relative_path: f for f in files}
    assert by_rel["top/wrap.zip/deep/a.log"].nested_depth == 1
    assert by_rel["top/wrap.zip/deep/a.log"].temp_path.read_bytes() == b"AAA"
    assert by_rel["top/note.txt"].nested_depth == 0
