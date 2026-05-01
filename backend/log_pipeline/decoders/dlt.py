from __future__ import annotations

import logging
import re
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Iterator, Optional

from log_pipeline.decoders.base import BaseDecoder
from log_pipeline.interfaces import ControllerType, DecodedLine

logger = logging.getLogger(__name__)

_DLT_PATTERN = b"DLT\x01"
_STORAGE_HEADER_LEN = 16
_STD_HEADER_FIXED = 4
_EXT_HEADER_LEN = 10
_MAX_REASONABLE_MSG_LEN = 64 * 1024  # spec ceiling is 65535
_PRINTABLE_RUN = re.compile(rb"[\x20-\x7e\t]{3,}")

# HTYP flag bits
_UEH = 0x01
_MSBF = 0x02
_WEID = 0x04
_WSID = 0x08
_WTMS = 0x10


@dataclass(frozen=True)
class DltMessage:
    storage_seconds: int
    storage_micros: int
    storage_ecu: str
    apid: str
    ctid: str
    payload: bytes
    msbf: bool


def _ascii4(buf: bytes) -> str:
    return buf.rstrip(b"\x00").decode("ascii", errors="replace")


def _format_ts(seconds: int, micros: int) -> str:
    """Format storage-header time as ISO8601 UTC with microsecond precision."""
    if micros < 0 or micros >= 1_000_000:
        micros = 0
    try:
        dt = datetime.fromtimestamp(seconds, tz=timezone.utc).replace(microsecond=micros)
    except (OSError, OverflowError, ValueError):
        return f"raw:{seconds}.{micros:06d}"
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")


def _scan_to_pattern(f: BinaryIO, max_skip: int = 1 << 20) -> bool:
    """Advance ``f`` to the next ``DLT\\x01`` pattern. Return True if found."""
    skipped = 0
    chunk_size = 4096
    while skipped < max_skip:
        pos = f.tell()
        chunk = f.read(chunk_size)
        if not chunk:
            return False
        idx = chunk.find(_DLT_PATTERN)
        if idx >= 0:
            f.seek(pos + idx)
            return True
        # back off 3 bytes so we can detect a pattern that straddles the boundary
        f.seek(pos + max(0, len(chunk) - 3))
        skipped += max(1, len(chunk) - 3)
    return False


def _printable_payload(payload: bytes) -> str:
    """Extract printable ASCII runs from a DLT payload.

    DLT verbose payloads sandwich strings between type-info / length / null bytes;
    we don't try to recover the structured arguments — we just surface the human
    readable parts so logs are grep-friendly.
    """
    runs = _PRINTABLE_RUN.findall(payload)
    if runs:
        return " ".join(r.decode("ascii", errors="replace").strip() for r in runs)
    return payload.hex()


def iter_dlt_messages(file_path: Path) -> Iterator[DltMessage]:
    """Streaming DLT message parser. Tolerates corruption by re-syncing on the magic."""
    with open(file_path, "rb") as f:
        while True:
            magic = f.read(_STORAGE_HEADER_LEN)
            if len(magic) < _STORAGE_HEADER_LEN:
                return
            if magic[:4] != _DLT_PATTERN:
                f.seek(-_STORAGE_HEADER_LEN + 1, 1)
                if not _scan_to_pattern(f):
                    return
                continue

            seconds = struct.unpack("<I", magic[4:8])[0]
            micros = struct.unpack("<i", magic[8:12])[0]
            ecu_storage = _ascii4(magic[12:16])

            std = f.read(_STD_HEADER_FIXED)
            if len(std) < _STD_HEADER_FIXED:
                return
            htyp, mcnt, msg_len = struct.unpack(">BBH", std)
            if msg_len < _STD_HEADER_FIXED or msg_len > _MAX_REASONABLE_MSG_LEN:
                logger.debug("dlt: implausible msg_len=%d, resyncing", msg_len)
                if not _scan_to_pattern(f):
                    return
                continue

            remaining = msg_len - _STD_HEADER_FIXED
            optional = b""
            if remaining > 0:
                optional_len = (
                    (4 if htyp & _WEID else 0)
                    + (4 if htyp & _WSID else 0)
                    + (4 if htyp & _WTMS else 0)
                )
                if optional_len > remaining:
                    if not _scan_to_pattern(f):
                        return
                    continue
                optional = f.read(optional_len)
                remaining -= optional_len

            apid = ctid = ""
            if htyp & _UEH:
                if remaining < _EXT_HEADER_LEN:
                    if not _scan_to_pattern(f):
                        return
                    continue
                ext = f.read(_EXT_HEADER_LEN)
                _msin, _noar, apid_b, ctid_b = struct.unpack(">BB4s4s", ext)
                apid = _ascii4(apid_b)
                ctid = _ascii4(ctid_b)
                remaining -= _EXT_HEADER_LEN

            if remaining < 0 or remaining > _MAX_REASONABLE_MSG_LEN:
                if not _scan_to_pattern(f):
                    return
                continue
            payload = f.read(remaining)
            if len(payload) < remaining:
                return

            yield DltMessage(
                storage_seconds=seconds,
                storage_micros=micros,
                storage_ecu=ecu_storage,
                apid=apid,
                ctid=ctid,
                payload=payload,
                msbf=bool(htyp & _MSBF),
            )


class DLTDecoder(BaseDecoder):
    controller = ControllerType.TBOX

    def can_decode(self, file_path: Path) -> bool:
        try:
            with open(file_path, "rb") as f:
                head = f.read(4)
        except OSError:
            return False
        return head == _DLT_PATTERN

    def writes_decoded_file(self) -> bool:
        return True

    def iter_lines(self, file_path: Path) -> Iterator[DecodedLine]:
        line_no = 0
        # byte_offset is set to the cumulative length of decoded lines, NOT the position
        # in the source DLT file — for binary sources we index against the .decoded.log.
        byte_offset = 0
        for msg in iter_dlt_messages(file_path):
            ts_str = _format_ts(msg.storage_seconds, msg.storage_micros)
            payload_text = _printable_payload(msg.payload)
            text = f"{ts_str} {msg.storage_ecu} {msg.apid} {msg.ctid} {payload_text}"
            raw_ts = msg.storage_seconds + max(msg.storage_micros, 0) / 1_000_000.0
            yield DecodedLine(
                line_no=line_no, byte_offset=byte_offset, raw_timestamp=raw_ts, text=text
            )
            byte_offset += len(text.encode("utf-8")) + 1  # +1 for the newline added on write
            line_no += 1
