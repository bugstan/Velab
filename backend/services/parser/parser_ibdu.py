"""
iBDU parser for real logs.

Supported line example:
[2025.09.11 04:05:55.100]RST:00 00 00 00 86 0E 00 00 96 10
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, Optional

from .base import BaseParser, ParsedEvent, EventLevel, EventType


class IBDUParser(BaseParser):
    PATTERN = re.compile(r"^\[(?P<ts>\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{1,3})\](?P<message>.*)$")

    def __init__(self):
        super().__init__(source_type="ibdu", parser_name="parser_ibdu", parser_version="2.0.0")

    def parse_file(
        self,
        file_path: Path,
        time_window: Optional[tuple[datetime, datetime]] = None,
        max_lines: Optional[int] = None,
    ) -> Iterator[ParsedEvent]:
        if not file_path.exists():
            raise FileNotFoundError(f"日志文件不存在: {file_path}")

        for line_number, line in enumerate(file_path.open("r", encoding="utf-8", errors="ignore"), 1):
            if max_lines and line_number > max_lines:
                break
            event = self.parse_line(line.rstrip("\n\r"), line_number)
            if event and not self._should_skip_line(event.original_ts, time_window):
                yield event

    def parse_line(self, line: str, line_number: int, context: Optional[Dict] = None) -> Optional[ParsedEvent]:
        m = self.PATTERN.match(line)
        if not m:
            return None

        ts = datetime.strptime(m.group("ts").ljust(23, "0"), "%Y.%m.%d %H:%M:%S.%f")
        message = m.group("message").strip()

        level = self._infer_level(message)
        event_type = EventType.ERROR if level in (EventLevel.ERROR, EventLevel.FATAL) else EventType.LOG
        if "fota" in message.lower() or "upgrade" in message.lower():
            event_type = EventType.FOTA_STAGE

        return self._create_event(
            message=message,
            raw_line_number=line_number,
            original_ts=ts,
            event_type=event_type,
            level=level,
            module="IBDU",
            raw_snippet=line,
            parsed_fields={
                "prefix": message.split(":", 1)[0] if ":" in message else "",
                "hex_payload": message,
            },
        )

    @staticmethod
    def _infer_level(message: str) -> EventLevel:
        msg = message.lower()
        if any(k in msg for k in ["fatal", "panic", "abort"]):
            return EventLevel.FATAL
        if any(k in msg for k in ["error", "failed", "fail"]):
            return EventLevel.ERROR
        if any(k in msg for k in ["warn", "timeout", "retry"]):
            return EventLevel.WARN
        if any(k in msg for k in ["debug", "trace"]):
            return EventLevel.DEBUG
        return EventLevel.INFO
