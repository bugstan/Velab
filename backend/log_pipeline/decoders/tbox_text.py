from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from log_pipeline.decoders.base import BaseDecoder, iter_text_lines
from log_pipeline.interfaces import ControllerType, DecodedLine

# Generic ISO8601-ish timestamp at line start: 2025-07-04 05:34:36.851679 / .851 / ,851
_GENERIC_TS_RE = re.compile(
    r"^.{0,40}?(?P<y>\d{4})-(?P<mo>\d{2})-(?P<d>\d{2})[T\s]"
    r"(?P<hh>\d{2}):(?P<mm>\d{2}):(?P<ss>\d{2})(?:[\.,](?P<frac>\d{1,9}))?"
)


def parse_generic_timestamp(text: str) -> Optional[float]:
    m = _GENERIC_TS_RE.match(text)
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
    frac = 0.0
    if m.group("frac"):
        s = m.group("frac")
        frac = int(s) / (10 ** len(s))
    return dt.timestamp() + frac


class TboxTextDecoder(BaseDecoder):
    """Fallback for tbox-class files that aren't DLT — activelog text, plain logs.

    DLT files are filtered out via ``can_decode`` so the registry can fall through.
    """

    controller = ControllerType.TBOX

    def can_decode(self, file_path: Path) -> bool:
        try:
            with open(file_path, "rb") as f:
                head = f.read(4096)
        except OSError:
            return False
        if head[:4] == b"DLT\x01":
            return False
        # binary heuristic: many NULs in head → not text
        if head.count(b"\x00") > len(head) // 8:
            return False
        return True

    def iter_lines(self, file_path: Path) -> Iterator[DecodedLine]:
        for line_no, byte_offset, text in iter_text_lines(file_path):
            ts = parse_generic_timestamp(text)
            yield DecodedLine(line_no=line_no, byte_offset=byte_offset, raw_timestamp=ts, text=text)
