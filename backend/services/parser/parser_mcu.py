"""
MCU parser for real logs.

Supported line example:
&18869330 INF@OTA:Utty Rx Cmd: FOTAMODE:3 1 1 60000 1!
&18869328 INF@SYS:Sys Date: 2025 9 11_4:5:56
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterator, Optional

from .base import BaseParser, ParsedEvent, EventLevel, EventType


class MCUParser(BaseParser):
    TICK_PATTERN = re.compile(r"^&(\d+)\s+(\w+)@(\w+):(.*)$")
    SYSDATE_PATTERN = re.compile(
        r"^&(\d+)\s+\w+@SYS:Sys Date:\s+(\d{4})\s+(\d+)\s+(\d+)_(\d+):(\d+):(\d+)"
    )

    def __init__(self):
        super().__init__(source_type="mcu", parser_name="parser_mcu", parser_version="2.0.0")
        self._anchors: list[tuple[int, datetime]] = []

    def parse_file(
        self,
        file_path: Path,
        time_window: Optional[tuple[datetime, datetime]] = None,
        max_lines: Optional[int] = None,
    ) -> Iterator[ParsedEvent]:
        if not file_path.exists():
            raise FileNotFoundError(f"日志文件不存在: {file_path}")

        lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in lines:
            self._collect_anchor(line)

        for line_number, line in enumerate(lines, 1):
            if max_lines and line_number > max_lines:
                break
            event = self.parse_line(line, line_number)
            if event and not self._should_skip_line(event.original_ts, time_window):
                yield event

    def parse_line(self, line: str, line_number: int, context: Optional[Dict] = None) -> Optional[ParsedEvent]:
        m = self.TICK_PATTERN.match(line.strip())
        if not m:
            return None

        tick_ms = int(m.group(1))
        level_str = m.group(2)
        module = m.group(3)
        message = m.group(4).strip()

        original_ts = self._tick_to_wall(tick_ms)
        level = self._map_level(level_str, message)
        event_type = self._event_type(module, message, level)

        return self._create_event(
            message=message,
            raw_line_number=line_number,
            original_ts=original_ts,
            event_type=event_type,
            level=level,
            module=module,
            raw_snippet=line,
            parsed_fields={"tick_ms": tick_ms, "module": module},
        )

    def _collect_anchor(self, line: str) -> None:
        m = self.SYSDATE_PATTERN.match(line.strip())
        if not m:
            return
        tick = int(m.group(1))
        dt = datetime(
            int(m.group(2)), int(m.group(3)), int(m.group(4)),
            int(m.group(5)), int(m.group(6)), int(m.group(7))
        )
        self._anchors.append((tick, dt))

    def _tick_to_wall(self, tick_ms: int) -> Optional[datetime]:
        if not self._anchors:
            return None
        anchor_tick, anchor_dt = min(self._anchors, key=lambda x: abs(x[0] - tick_ms))
        return anchor_dt + timedelta(milliseconds=(tick_ms - anchor_tick))

    @staticmethod
    def _map_level(level_str: str, message: str) -> EventLevel:
        lv = level_str.upper()
        if lv.startswith("ERR"):
            return EventLevel.ERROR
        if lv.startswith("WRN") or lv.startswith("WARN"):
            return EventLevel.WARN
        if lv.startswith("DBG"):
            return EventLevel.DEBUG
        if lv.startswith("FAT"):
            return EventLevel.FATAL
        if any(k in message.lower() for k in ["error", "failed", "panic"]):
            return EventLevel.ERROR
        return EventLevel.INFO

    @staticmethod
    def _event_type(module: str, message: str, level: EventLevel) -> EventType:
        msg = message.lower()
        mod = module.lower()
        if level in (EventLevel.ERROR, EventLevel.FATAL):
            return EventType.ERROR
        if mod == "ota" or "fota" in msg or "upgrade" in msg:
            return EventType.FOTA_STAGE
        if mod in ("com", "can"):
            return EventType.NETWORK
        if mod == "sys":
            return EventType.SYSTEM
        return EventType.LOG
