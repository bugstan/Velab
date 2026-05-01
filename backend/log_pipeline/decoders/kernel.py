from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from log_pipeline.decoders.android_logcat import _LOGCAT_LINE_RE, parse_logcat_timestamp
from log_pipeline.decoders.base import BaseDecoder, infer_year_hint, iter_text_lines
from log_pipeline.interfaces import ControllerType, DecodedLine, is_effective_wall_clock_ts

_DMESG_LINE_RE = re.compile(r"^\[\s*(?P<sec>\d+)\.(?P<usec>\d+)\]")

_BOOT_CAPTURE_FILENAME_RE = re.compile(
    r"^(?P<idx>\d+)_(?P<date>\d{4}-\d{2}-\d{2})_(?P<time>\d{2}-\d{2}-\d{2})\.log$"
)

_KERNEL_DUMP_FILENAME_RE = re.compile(
    r"^kernel@(?P<date>\d{4}-\d{2}-\d{2})_(?P<time>\d{2}-\d{2}-\d{2})(?:\.\d+)?\.log$"
)


def parse_boot_capture_filename(name: str) -> Optional[tuple[int, float]]:
    """Parse boot-capture filenames like ``200_2025-09-12_11-09-34.log``.

    Returns ``(boot_index, wall_clock_epoch)`` or ``None`` if the name does not
    match. The wall-clock time is treated as UTC — the device timezone is not
    encoded in the name, and the rest of the pipeline is UTC throughout.
    """
    m = _BOOT_CAPTURE_FILENAME_RE.match(name)
    if not m:
        return None
    try:
        dt = datetime.strptime(
            f"{m.group('date')} {m.group('time').replace('-', ':')}",
            "%Y-%m-%d %H:%M:%S",
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    ts = dt.timestamp()
    if not is_effective_wall_clock_ts(ts):
        return None
    return int(m.group("idx")), ts


def is_boot_capture_path(bundle_relative_path: str, original_name: str) -> Optional[tuple[int, float]]:
    """True iff this file is a per-boot dmesg snapshot under ``kernel_logs/``.

    Both the parent directory AND the filename pattern must match — guards
    against accidentally matching unrelated files that happen to share the
    naming style.
    """
    if "/kernel_logs/" not in bundle_relative_path.replace("\\", "/"):
        return None
    return parse_boot_capture_filename(original_name)


def parse_kernel_dump_filename(name: str) -> Optional[float]:
    """Parse runtime-kernel ringbuffer dump filenames like
    ``kernel@2025-09-11_13-27-05.554.log``.

    Returns the dump wall-clock epoch (UTC), or ``None`` if the name does not
    match. The wall-clock represents *when the dump was written* — the latest
    entry inside the file is treated as having been emitted at this moment.
    Ignores invalid RTC sentinel dates (``1970-*`` and ``2020-01-01``) — those
    files have no usable filename anchor.
    """
    m = _KERNEL_DUMP_FILENAME_RE.match(name)
    if not m:
        return None
    date_str = m.group("date")
    if date_str.startswith("1970-") or date_str == "2020-01-01":
        return None
    try:
        dt = datetime.strptime(
            f"{date_str} {m.group('time').replace('-', ':')}",
            "%Y-%m-%d %H:%M:%S",
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    ts = dt.timestamp()
    if not is_effective_wall_clock_ts(ts):
        return None
    return ts


def parse_dmesg_relative(text: str) -> Optional[float]:
    """Return seconds-since-boot as a relative timestamp.

    Note: this is *relative*, not unix epoch. Alignment stage corrects against an anchor.
    Values below MIN_VALID_TS (2020) are correctly treated as unsynced by prescan.
    """
    m = _DMESG_LINE_RE.match(text)
    if not m:
        return None
    return int(m.group("sec")) + int(m.group("usec")) / 1_000_000.0


class KernelDmesgDecoder(BaseDecoder):
    controller = ControllerType.KERNEL

    def can_decode(self, file_path: Path) -> bool:
        try:
            with open(file_path, "rb") as f:
                head = f.read(4096)
        except OSError:
            return False
        for raw in head.splitlines():
            if _DMESG_LINE_RE.match(raw.decode("utf-8", errors="replace")):
                return True
        return False

    def iter_lines(self, file_path: Path) -> Iterator[DecodedLine]:
        for line_no, byte_offset, text in iter_text_lines(file_path):
            ts = parse_dmesg_relative(text)
            yield DecodedLine(line_no=line_no, byte_offset=byte_offset, raw_timestamp=ts, text=text)


class KernelLogcatDecoder(BaseDecoder):
    """For kernel/kernel.log files emitted in Android logcat MM-DD format."""

    controller = ControllerType.KERNEL

    def can_decode(self, file_path: Path) -> bool:
        try:
            with open(file_path, "rb") as f:
                head = f.read(4096)
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
