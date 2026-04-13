"""
Android logcat parser for real vehicle logs.

Supported line example:
09-12 11:24:22.028403   986   986 W NmeaOperation: nmea data report start
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from .base import BaseParser, ParsedEvent, EventLevel, EventType, registry


class AndroidParser(BaseParser):
    THREADTIME_PATTERN = re.compile(
        r'^(?P<month>\d{2})-(?P<day>\d{2})\s+'
        r'(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\.(?P<us>\d{1,6})\s+'
        r'(?P<pid>\d+)\s+'
        r'(?P<tid>\d+)\s+'
        r'(?P<level>[VDIWEF])\s+'
        r'(?P<tag>[^:]+):\s*'
        r'(?P<message>.*)$'
    )

    LEVEL_MAP = {
        "V": EventLevel.DEBUG,
        "D": EventLevel.DEBUG,
        "I": EventLevel.INFO,
        "W": EventLevel.WARN,
        "E": EventLevel.ERROR,
        "F": EventLevel.FATAL,
    }

    def __init__(self, year: int = 2025):
        super().__init__(
            source_type="android",
            parser_name="parser_android",
            parser_version="2.0.0",
        )
        self.year = year

    def parse_file(
        self,
        file_path: Path,
        time_window: Optional[tuple[datetime, datetime]] = None,
        max_lines: Optional[int] = None,
    ) -> Iterator[ParsedEvent]:
        if not file_path.exists():
            raise FileNotFoundError(f"日志文件不存在: {file_path}")

        for line_number, line in enumerate(
            file_path.open("r", encoding="utf-8", errors="ignore"), 1
        ):
            if max_lines and line_number > max_lines:
                break
            event = self.parse_line(line.rstrip("\n\r"), line_number)
            if event and not self._should_skip_line(event.original_ts, time_window):
                yield event

    def parse_line(self, line: str, line_number: int) -> Optional[ParsedEvent]:
        m = self.THREADTIME_PATTERN.match(line)
        if not m:
            return None

        g = m.groupdict()
        micro = int(g["us"].ljust(6, "0")[:6])
        original_ts = datetime(
            self.year,
            int(g["month"]),
            int(g["day"]),
            int(g["hour"]),
            int(g["minute"]),
            int(g["second"]),
            micro,
        )

        level = self.LEVEL_MAP.get(g["level"], EventLevel.INFO)
        tag = g["tag"].strip()
        message = g["message"].strip()

        event_type = EventType.ERROR if level in (EventLevel.ERROR, EventLevel.FATAL) else EventType.LOG

        return self._create_event(
            message=message,
            raw_line_number=line_number,
            original_ts=original_ts,
            event_type=event_type,
            level=level,
            module=tag,
            process=g["pid"],
            thread=g["tid"],
            tag=tag,
            raw_snippet=line,
            parsed_fields={"pid": int(g["pid"]), "tid": int(g["tid"]), "tag": tag},
        )


registry.register("android", AndroidParser)
