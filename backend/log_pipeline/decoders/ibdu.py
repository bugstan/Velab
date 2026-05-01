from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from log_pipeline.decoders.base import BaseDecoder, iter_text_lines
from log_pipeline.interfaces import ControllerType, DecodedLine


_IBDU_LINE_RE = re.compile(
    r"^\[(?P<y>\d{4})\.(?P<mo>\d{2})\.(?P<d>\d{2})\s+"
    r"(?P<hh>\d{2}):(?P<mm>\d{2}):(?P<ss>\d{2})\.(?P<ms>\d{3})\](?P<payload>.*)$"
)

_HEX_CHARS = frozenset("0123456789abcdefABCDEF")


def parse_ibdu_timestamp(text: str) -> Optional[float]:
    m = _IBDU_LINE_RE.match(text)
    if not m:
        return None
    try:
        dt = datetime(
            year=int(m.group("y")),
            month=int(m.group("mo")),
            day=int(m.group("d")),
            hour=int(m.group("hh")),
            minute=int(m.group("mm")),
            second=int(m.group("ss")),
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None
    return dt.timestamp() + int(m.group("ms")) / 1000.0


def _render_bytes(b: bytes) -> str:
    return "".join(chr(x) if 0x20 <= x <= 0x7E else "." for x in b)


def decode_ibdu_payload(payload: str) -> str:
    """Substitute every maximal even-length hex run of length >= 4 with its
    ASCII rendering (non-printable bytes shown as ``.``). Leaves shorter or
    odd-length runs intact so plain-ASCII tags like ``err_`` survive untouched.
    """
    out: list[str] = []
    i = 0
    n = len(payload)
    while i < n:
        if payload[i] in _HEX_CHARS:
            j = i
            while j < n and payload[j] in _HEX_CHARS:
                j += 1
            run_len = j - i
            if run_len >= 4 and run_len % 2 == 0:
                try:
                    raw = bytes.fromhex(payload[i:j])
                    out.append(_render_bytes(raw))
                except ValueError:
                    out.append(payload[i:j])
            else:
                out.append(payload[i:j])
            i = j
        else:
            out.append(payload[i])
            i += 1
    return "".join(out)


def _format_decoded_line(text: str) -> Optional[tuple[str, float]]:
    """Return ``(decoded_text, raw_ts_seconds)`` or ``None`` if the line is not
    a recognised iBDU record. Decoded form is DLT-replay-friendly (T separator,
    matches ``parse_dlt_decoded_timestamp``)."""
    m = _IBDU_LINE_RE.match(text)
    if not m:
        return None
    try:
        dt = datetime(
            year=int(m.group("y")),
            month=int(m.group("mo")),
            day=int(m.group("d")),
            hour=int(m.group("hh")),
            minute=int(m.group("mm")),
            second=int(m.group("ss")),
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None
    ts = dt.timestamp() + int(m.group("ms")) / 1000.0
    payload = m.group("payload")
    decoded = decode_ibdu_payload(payload)
    iso = dt.strftime("%Y-%m-%dT%H:%M:%S") + f".{m.group('ms')}"
    if decoded != payload:
        return f"{iso} {decoded} (raw={payload})", ts
    return f"{iso} {payload}", ts


class IBDUDecoder(BaseDecoder):
    """iBDU low-level debug log: ``[YYYY.MM.DD HH:MM:SS.mmm]<hex+ASCII>``.

    Writes a ``.decoded.log`` with the timestamp normalised to ISO and the hex
    payload rendered as inline ASCII (non-printable → ``.``). Also keeps the
    original hex string after ``raw=`` so forensic checks can recover the
    bytes.
    """

    controller = ControllerType.IBDU

    def can_decode(self, file_path: Path) -> bool:
        try:
            with open(file_path, "rb") as f:
                head = f.read(2048)
        except OSError:
            return False
        if head[:2] == b"\x1f\x8b" or head[:4] == b"PK\x03\x04":
            return False
        for raw in head.splitlines():
            try:
                line = raw.decode("utf-8", errors="replace")
            except Exception:
                continue
            if _IBDU_LINE_RE.match(line):
                return True
        return False

    def writes_decoded_file(self) -> bool:
        return True

    def iter_lines(self, file_path: Path) -> Iterator[DecodedLine]:
        for line_no, byte_offset, text in iter_text_lines(file_path):
            res = _format_decoded_line(text)
            if res is None:
                yield DecodedLine(
                    line_no=line_no, byte_offset=byte_offset, raw_timestamp=None, text=text
                )
                continue
            decoded_text, ts = res
            yield DecodedLine(
                line_no=line_no, byte_offset=byte_offset, raw_timestamp=ts, text=decoded_text
            )
