from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from log_pipeline.decoders.base import BaseDecoder, iter_text_lines
from log_pipeline.interfaces import ControllerType, DecodedLine

# Java logback / Android format: 2025-08-07 08:35:08,511 LEVEL ...
# Also accept dot-millis: 2025-08-07 08:35:08.511 ...
_FOTA_LINE_RE = re.compile(
    r"^(?P<y>\d{4})-(?P<mo>\d{2})-(?P<d>\d{2})\s+"
    r"(?P<hh>\d{2}):(?P<mm>\d{2}):(?P<ss>\d{2})[,.](?P<ms>\d{3})\s+"
)


def parse_fota_timestamp(text: str) -> Optional[float]:
    m = _FOTA_LINE_RE.match(text)
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


class FotaTextDecoder(BaseDecoder):
    controller = ControllerType.FOTA

    def can_decode(self, file_path: Path) -> bool:
        # accept any file that classifier routed here; format detection is best-effort
        # but we exclude obvious non-text artefacts
        name = Path(file_path).name.lower()
        if name.endswith((".db", ".db-journal", ".bin")):
            return False
        try:
            with open(file_path, "rb") as f:
                head = f.read(2048)
        except OSError:
            return False
        if b"\x00" in head[:512]:
            return False
        return True

    def iter_lines(self, file_path: Path) -> Iterator[DecodedLine]:
        for line_no, byte_offset, text in iter_text_lines(file_path):
            ts = parse_fota_timestamp(text)
            yield DecodedLine(line_no=line_no, byte_offset=byte_offset, raw_timestamp=ts, text=text)
