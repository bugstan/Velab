from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from log_pipeline.decoders.base import BaseDecoder, infer_year_hint, iter_text_lines
from log_pipeline.interfaces import ControllerType, DecodedLine

_LOGCAT_LINE_RE = re.compile(
    r"^(?P<mon>\d{2})-(?P<day>\d{2})\s+"
    r"(?P<hh>\d{2}):(?P<mm>\d{2}):(?P<ss>\d{2})\.(?P<frac>\d{3,6})\s+"
    r"\d+\s+\d+\s+[VDIWEF]\s+"
)


def parse_logcat_timestamp(text: str, year: int) -> Optional[float]:
    m = _LOGCAT_LINE_RE.match(text)
    if not m:
        return None
    frac_str = m.group("frac")
    frac = int(frac_str) / (10 ** len(frac_str))
    try:
        dt = datetime(
            year=year,
            month=int(m.group("mon")),
            day=int(m.group("day")),
            hour=int(m.group("hh")),
            minute=int(m.group("mm")),
            second=int(m.group("ss")),
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None
    return dt.timestamp() + frac


class AndroidLogcatDecoder(BaseDecoder):
    controller = ControllerType.ANDROID

    def can_decode(self, file_path: Path) -> bool:
        try:
            with open(file_path, "rb") as f:
                head = f.read(2048)
        except OSError:
            return False
        for raw in head.splitlines():
            if _LOGCAT_LINE_RE.match(raw.decode("utf-8", errors="replace")):
                return True
        return False

    def iter_lines(self, file_path: Path) -> Iterator[DecodedLine]:
        year = infer_year_hint(file_path)
        for line_no, byte_offset, text in iter_text_lines(file_path):
            ts = parse_logcat_timestamp(text, year)
            yield DecodedLine(line_no=line_no, byte_offset=byte_offset, raw_timestamp=ts, text=text)
