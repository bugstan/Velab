"""
DLT parser for real logs.

Extracts text records from DLT binary/plain files with embedded timestamps:
2025-09-11 00:05:52.391679:fota_state_refresh.cppL[1282] tid:[23456]:message
1970-01-01 00:00:55.619666:fota_api_mcu.cppL[954] tid:[11111]:message
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, Optional

from .base import BaseParser, ParsedEvent, EventLevel, EventType


class DLTParser(BaseParser):
    PATTERN = re.compile(
        r"(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+):"
        r"(?P<src>\S+)\s+tid:\[(?P<tid>\d+)\]:(?P<message>.*)"
    )

    def __init__(self):
        super().__init__(source_type="dlt", parser_name="parser_dlt", parser_version="2.0.0")

    def parse_file(
        self,
        file_path: Path,
        time_window: Optional[tuple[datetime, datetime]] = None,
        max_lines: Optional[int] = None,
    ) -> Iterator[ParsedEvent]:
        if not file_path.exists():
            raise FileNotFoundError(f"日志文件不存在: {file_path}")

        raw = file_path.read_bytes().decode("utf-8", errors="ignore")
        line_number = 0
        for line in raw.splitlines():
            line_number += 1
            if max_lines and line_number > max_lines:
                break
            event = self.parse_line(line, line_number)
            if event and not self._should_skip_line(event.original_ts, time_window):
                yield event

    def parse_line(self, line: str, line_number: int, context: Optional[Dict] = None) -> Optional[ParsedEvent]:
        m = self.PATTERN.search(line)
        if not m:
            return None

        g = m.groupdict()
        ts = datetime.strptime(g["ts"][:26], "%Y-%m-%d %H:%M:%S.%f")
        source_file = g["src"]
        message = g["message"].strip()

        level = self._infer_level(message)
        event_type = self._infer_event_type(message, level)
        module = source_file.split("/")[-1].split(".")[0]

        parsed_fields = {
            "source_file": source_file,
            "tid": int(g["tid"]),
            "is_epoch_clock": ts.year == 1970,
        }

        return self._create_event(
            message=message,
            raw_line_number=line_number,
            original_ts=ts,
            event_type=event_type,
            level=level,
            module=module,
            raw_snippet=line,
            thread=g["tid"],
            parsed_fields=parsed_fields,
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

    @staticmethod
    def _infer_event_type(message: str, level: EventLevel) -> EventType:
        msg = message.lower()
        if level in (EventLevel.ERROR, EventLevel.FATAL):
            return EventType.ERROR
        if any(k in msg for k in ["fota", "upgrade", "onmcuindication", "refreshprogress"]):
            return EventType.FOTA_STAGE
        if any(k in msg for k in ["modem", "socket", "network"]):
            return EventType.NETWORK
        return EventType.LOG
