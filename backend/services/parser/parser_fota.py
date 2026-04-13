"""
FOTA HMI parser for real logs.

Supported line example:
2000-01-01 00:01:09,856 DEBUG (FotaHMIServiceImpl.java:232)- [FotaHMIServiceImpl-SOA]-IcgmLinkNotify  LinkSts: 1
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from .base import BaseParser, ParsedEvent, EventLevel, EventType, registry


class FotaParser(BaseParser):
    PATTERN = re.compile(
        r'^(?P<date>\d{4}-\d{2}-\d{2})\s+'
        r'(?P<time>\d{2}:\d{2}:\d{2},\d{3})\s+'
        r'(?P<level>[A-Z]+)\s+'
        r'\((?P<src>[^)]+)\)-\s+'
        r'\[(?P<tag>[^\]]+)\]-(?P<message>.*)$'
    )

    LEVEL_MAP = {
        "TRACE": EventLevel.DEBUG,
        "DEBUG": EventLevel.DEBUG,
        "INFO": EventLevel.INFO,
        "WARN": EventLevel.WARN,
        "WARNING": EventLevel.WARN,
        "ERROR": EventLevel.ERROR,
        "FATAL": EventLevel.FATAL,
    }

    def __init__(self):
        super().__init__(
            source_type="fota_hmi",
            parser_name="parser_fota_hmi",
            parser_version="2.0.0",
        )

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
        m = self.PATTERN.match(line)
        if not m:
            return None

        g = m.groupdict()
        dt = datetime.strptime(f"{g['date']} {g['time']}", "%Y-%m-%d %H:%M:%S,%f")
        level = self.LEVEL_MAP.get(g["level"], EventLevel.INFO)
        tag = g["tag"].strip()
        message = g["message"].strip()
        module = tag

        event_type = EventType.FOTA_STAGE if any(
            kw in message.lower() for kw in ["fota", "upgrade", "icgmlinknotify", "showupgraderesult"]
        ) else (EventType.ERROR if level in (EventLevel.ERROR, EventLevel.FATAL) else EventType.LOG)

        return self._create_event(
            message=message,
            raw_line_number=line_number,
            original_ts=dt,
            event_type=event_type,
            level=level,
            module=module,
            tag=tag,
            raw_snippet=line,
            parsed_fields={
                "source_file": g["src"],
                "tag": tag,
                "is_uptime_clock": g["date"] == "2000-01-01",
            },
        )


registry.register("fota_hmi", FotaParser)
