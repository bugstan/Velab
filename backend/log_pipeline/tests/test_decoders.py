from __future__ import annotations

import os
import struct
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from log_pipeline.decoders.android_logcat import AndroidLogcatDecoder, parse_logcat_timestamp
from log_pipeline.decoders.base import default_registry, infer_year_hint, iter_text_lines
from log_pipeline.decoders.dlt import DLTDecoder, _format_ts, iter_dlt_messages
from log_pipeline.decoders.fota_text import FotaTextDecoder, parse_fota_timestamp
from log_pipeline.decoders.kernel import (
    KernelDmesgDecoder,
    KernelLogcatDecoder,
    parse_boot_capture_filename,
    parse_dmesg_relative,
    parse_kernel_dump_filename,
)
from log_pipeline.decoders.tbox_text import TboxTextDecoder, parse_generic_timestamp
from log_pipeline.interfaces import ControllerType


# ---------------- helpers ----------------


def _epoch(y, mo, d, h, m, s, frac=0.0) -> float:
    return datetime(y, mo, d, h, m, s, tzinfo=timezone.utc).timestamp() + frac


# ---------------- year hint ----------------


def test_infer_year_from_filename(tmp_path: Path):
    p = tmp_path / "saicmaxus@2025-08-07_09-21-54.665.log"
    p.write_text("hi", encoding="utf-8")
    assert infer_year_hint(p) == 2025


def test_infer_year_from_mtime_when_filename_silent(tmp_path: Path):
    p = tmp_path / "anonymous.log"
    p.write_text("hi", encoding="utf-8")
    target = datetime(2024, 6, 1, tzinfo=timezone.utc).timestamp()
    os.utime(p, (target, target))
    assert infer_year_hint(p) == 2024


# ---------------- iter_text_lines byte_offset ----------------


def test_iter_text_lines_byte_offsets(tmp_path: Path):
    p = tmp_path / "a.log"
    data = b"first\nsecond line\nthird\n"
    p.write_bytes(data)
    out = list(iter_text_lines(p))
    assert [(n, off, t) for n, off, t in out] == [
        (0, 0, "first"),
        (1, 6, "second line"),
        (2, 18, "third"),
    ]


def test_iter_text_lines_handles_bom(tmp_path: Path):
    p = tmp_path / "bom.log"
    p.write_bytes(b"\xef\xbb\xbfhello\n")
    out = list(iter_text_lines(p))
    assert out == [(0, 3, "hello")]


# ---------------- android logcat ----------------


def test_logcat_timestamp_parse():
    ts = parse_logcat_timestamp(
        "09-12 11:24:22.028403   986   986 W Tag: msg", year=2025
    )
    assert ts == pytest.approx(_epoch(2025, 9, 12, 11, 24, 22, 0.028403), rel=1e-9)


def test_logcat_timestamp_3digit_millis():
    ts = parse_logcat_timestamp("09-12 11:24:22.028   986   986 W Tag: msg", year=2025)
    assert ts == pytest.approx(_epoch(2025, 9, 12, 11, 24, 22, 0.028), rel=1e-9)


def test_logcat_timestamp_returns_none_for_dmesg_line():
    assert parse_logcat_timestamp("[    0.000000] Booting", year=2025) is None


def test_android_decoder_can_decode_and_iter(tmp_path: Path):
    p = tmp_path / "saicmaxus@2025-08-07_09-21-54.665.log"
    p.write_text(
        "09-12 11:24:22.028403   986   986 W TagA: hello\n"
        "09-12 11:24:22.030000   986   986 E TagB: error here\n"
        "[ junk] not a real logcat line\n",
        encoding="utf-8",
    )
    d = AndroidLogcatDecoder()
    assert d.can_decode(p)
    lines = list(d.iter_lines(p))
    assert len(lines) == 3
    assert lines[0].raw_timestamp is not None
    assert lines[2].raw_timestamp is None
    assert lines[0].byte_offset == 0
    assert lines[1].byte_offset == len(b"09-12 11:24:22.028403   986   986 W TagA: hello\n")


# ---------------- fota text ----------------


def test_fota_timestamp_parse_comma_millis():
    assert parse_fota_timestamp("2025-08-07 08:35:08,511 DEBUG msg") == pytest.approx(
        _epoch(2025, 8, 7, 8, 35, 8, 0.511), rel=1e-9
    )


def test_fota_timestamp_parse_dot_millis():
    assert parse_fota_timestamp("2025-08-07 08:35:08.511 DEBUG msg") == pytest.approx(
        _epoch(2025, 8, 7, 8, 35, 8, 0.511), rel=1e-9
    )


def test_fota_decoder_can_decode_skips_db(tmp_path: Path):
    db = tmp_path / "fotapackage.db"
    db.write_bytes(b"SQLite format 3\x00")
    assert FotaTextDecoder().can_decode(db) is False


def test_fota_decoder_iter(tmp_path: Path):
    p = tmp_path / "fotaHMI_2025-08-07.0.log"
    p.write_text(
        "2025-08-07 08:35:08,511 DEBUG (Log.java:45)- [Init]-start\n"
        "2025-08-07 08:35:08,632 WARN (Log.java:59)- [App]-warn\n"
        "blank line not parsed\n",
        encoding="utf-8",
    )
    lines = list(FotaTextDecoder().iter_lines(p))
    assert len(lines) == 3
    assert lines[0].raw_timestamp == pytest.approx(_epoch(2025, 8, 7, 8, 35, 8, 0.511))
    assert lines[2].raw_timestamp is None


# ---------------- kernel dmesg ----------------


def test_dmesg_relative_parse():
    assert parse_dmesg_relative("[    0.000000] Booting Linux") == 0.0
    assert parse_dmesg_relative("[   12.345678] foo") == pytest.approx(12.345678)
    assert parse_dmesg_relative("not a dmesg line") is None


def test_kernel_dmesg_decoder(tmp_path: Path):
    p = tmp_path / "176_2025-09-10_14-44-01.log"
    p.write_text(
        "[    0.000000] Booting Linux on physical CPU 0x0\n"
        "[    1.234567] random: crng init done\n",
        encoding="utf-8",
    )
    d = KernelDmesgDecoder()
    assert d.can_decode(p)
    lines = list(d.iter_lines(p))
    assert [ln.raw_timestamp for ln in lines] == [0.0, pytest.approx(1.234567)]


def test_kernel_filename_anchors_filter_unsynced_dates():
    assert parse_boot_capture_filename("1_1970-01-01_00-00-00.log") is None
    assert parse_boot_capture_filename("1_2020-01-01_12-34-56.log") is None
    assert parse_boot_capture_filename("1_2020-01-02_00-00-00.log") is not None

    assert parse_kernel_dump_filename("kernel@1970-01-01_00-00-00.log") is None
    assert parse_kernel_dump_filename("kernel@2020-01-01_12-34-56.log") is None
    assert parse_kernel_dump_filename("kernel@2020-01-02_00-00-00.log") is not None


def test_kernel_logcat_decoder_for_kernel_dot_log(tmp_path: Path):
    p = tmp_path / "kernel@2025-09-11_07-13-33.log"
    p.write_text(
        "01-01 10:15:53.554983   695   695 E [STS_TS/E]sts_read: i2c fail\n",
        encoding="utf-8",
    )
    d = KernelLogcatDecoder()
    assert d.can_decode(p)
    [ln] = list(d.iter_lines(p))
    # year hint = 2025 (from filename); month-day = 01-01
    assert ln.raw_timestamp is not None
    assert ln.raw_timestamp == pytest.approx(_epoch(2025, 1, 1, 10, 15, 53, 0.554983))


# ---------------- tbox text ----------------


def test_generic_timestamp_with_microseconds():
    ts = parse_generic_timestamp("2025-07-04 05:34:36.851679:init.cpp")
    assert ts == pytest.approx(_epoch(2025, 7, 4, 5, 34, 36, 0.851679), rel=1e-9)


def test_tbox_text_rejects_dlt_header(tmp_path: Path):
    p = tmp_path / "trace.dlt"
    p.write_bytes(b"DLT\x01" + b"\x00" * 200)
    assert TboxTextDecoder().can_decode(p) is False


def test_tbox_text_iter(tmp_path: Path):
    p = tmp_path / "activelog_VIN_20250807083951"
    p.write_text(
        "2025-08-07 08:39:51 [ACTIVE] start\n"
        "2025-08-07 08:39:52 [ACTIVE] tick\n",
        encoding="utf-8",
    )
    lines = list(TboxTextDecoder().iter_lines(p))
    assert len(lines) == 2
    assert lines[0].raw_timestamp is not None


# ---------------- DLT ----------------


def _build_dlt_message(
    seconds: int,
    micros: int,
    ecu: bytes,
    apid: bytes,
    ctid: bytes,
    payload: bytes,
) -> bytes:
    """Synthesize one DLT message with storage header + standard + extended + payload."""
    storage = b"DLT\x01" + struct.pack("<I", seconds) + struct.pack("<i", micros) + ecu.ljust(4, b"\x00")
    htyp = 0x01 | 0x04  # UEH | WEID — version=0, MSBF off, no SID, no TMS
    htyp = htyp | (1 << 5)  # version = 1 in bits 5-7
    mcnt = 0
    weid_bytes = b"ECU1"
    ext_msin = 0
    ext_noar = 0
    ext = struct.pack(">BB4s4s", ext_msin, ext_noar, apid.ljust(4, b"\x00"), ctid.ljust(4, b"\x00"))
    body = weid_bytes + ext + payload
    msg_len = 4 + len(body)
    std = struct.pack(">BBH", htyp, mcnt, msg_len)
    return storage + std + body


def test_dlt_decoder_parses_synthetic_message(tmp_path: Path):
    p = tmp_path / "trace.dlt"
    payload = b"\x00\x82\x00\x00" + b"\x10\x00" + b"hello dlt\x00"  # type-info + length + str
    msg_bytes = _build_dlt_message(
        seconds=1751604876, micros=851679, ecu=b"TBOX", apid=b"MNT", ctid=b"MNT",
        payload=payload,
    )
    # Two messages back to back
    p.write_bytes(msg_bytes + msg_bytes)
    msgs = list(iter_dlt_messages(p))
    assert len(msgs) == 2
    m = msgs[0]
    assert m.storage_seconds == 1751604876
    assert m.storage_micros == 851679
    assert m.storage_ecu == "TBOX"
    assert m.apid == "MNT"
    assert m.ctid == "MNT"
    assert b"hello dlt" in m.payload


def test_dlt_decoder_iter_lines_format(tmp_path: Path):
    p = tmp_path / "trace.dlt"
    payload = b"\x00\x82\x00\x00\x10\x00hello dlt\x00"
    p.write_bytes(_build_dlt_message(1751604876, 851679, b"TBOX", b"MNT", b"MNT", payload))
    d = DLTDecoder()
    assert d.can_decode(p)
    [line] = list(d.iter_lines(p))
    assert "TBOX" in line.text
    assert "MNT" in line.text
    assert "hello dlt" in line.text
    assert line.raw_timestamp == pytest.approx(1751604876 + 851679 / 1e6)
    # decoded_format/writes flag
    assert d.writes_decoded_file() is True
    assert d.decoded_format() == "text"


def test_dlt_decoder_resyncs_on_corruption(tmp_path: Path):
    p = tmp_path / "corrupt.dlt"
    good = _build_dlt_message(1751604876, 0, b"TBOX", b"APP", b"CTX", b"\x00\x82\x00\x00\x05\x00hi\x00\x00\x00")
    junk = b"\x55" * 32  # garbage between messages
    p.write_bytes(junk + good + junk + good)
    msgs = list(iter_dlt_messages(p))
    assert len(msgs) == 2


def test_format_ts_iso():
    s = _format_ts(1751604876, 851679)
    assert s.startswith("2025-")
    assert s.endswith("851679")


# ---------------- registry ----------------


def test_registry_picks_dlt_for_tbox_dlt_file(tmp_path: Path):
    p = tmp_path / "trace.dlt"
    p.write_bytes(b"DLT\x01" + b"\x00" * 200)
    d = default_registry().find(ControllerType.TBOX, p)
    assert d.__class__.__name__ == "DLTDecoder"


def test_registry_picks_tbox_text_for_non_dlt_tbox(tmp_path: Path):
    p = tmp_path / "activelog_VIN"
    p.write_text("2025-08-07 08:39:51 hi\n", encoding="utf-8")
    d = default_registry().find(ControllerType.TBOX, p)
    assert d.__class__.__name__ == "TboxTextDecoder"


def test_registry_picks_dmesg_for_dmesg_format(tmp_path: Path):
    p = tmp_path / "176_2025-09-10_14-44-01.log"
    p.write_text("[    0.000000] Booting Linux\n", encoding="utf-8")
    d = default_registry().find(ControllerType.KERNEL, p)
    assert d.__class__.__name__ == "KernelDmesgDecoder"


def test_registry_picks_kernel_logcat_for_kernel_log(tmp_path: Path):
    p = tmp_path / "kernel@2025-09-11_07-13-33.log"
    p.write_text("01-01 10:15:53.554983   695   695 E Tag: msg\n", encoding="utf-8")
    d = default_registry().find(ControllerType.KERNEL, p)
    assert d.__class__.__name__ == "KernelLogcatDecoder"
