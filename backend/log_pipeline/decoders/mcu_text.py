from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, Optional

from log_pipeline.decoders.base import BaseDecoder, iter_text_lines
from log_pipeline.interfaces import BootSegment, ControllerType, DecodedLine


_MCU_TICK_RE = re.compile(r"^&(?P<tick>\d+)\s+(?:INF|WRN|ERR|DBG)@")

_MCU_CLOCK_SYNC_RE = re.compile(
    r"^&(?P<tick>\d+)\s+\w+@SYS\s*:\s*Set Date By Second:\s*(?P<epoch_2020>\d+)\s*,"
)

# 2020-01-01 00:00:00 UTC; the MCU advertises wall-clock as seconds-since-this.
_EPOCH_2020 = 1577836800.0


def parse_mcu_tick(text: str) -> Optional[float]:
    """Return seconds-since-boot from a ``&<tick_ms> ...`` line, or None."""
    m = _MCU_TICK_RE.match(text)
    if m is None:
        return None
    return int(m.group("tick")) / 1000.0


def _boot_wall_from_sync(tick_ms: int, epoch_2020: int) -> float:
    """``boot_wall = (EPOCH_2020 + epoch_2020) - tick_ms/1000``."""
    return _EPOCH_2020 + epoch_2020 - tick_ms / 1000.0


def detect_mcu_clock_offset(file_path: Path) -> Optional[tuple[float, float]]:
    """Single-boot legacy helper: scan for the first ``Set Date By Second:``
    line and return ``(boot_wall_epoch, confidence)``. Use
    :func:`detect_mcu_segments` for multi-boot files."""
    try:
        with open(file_path, "rb") as f:
            for raw in f:
                text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                m = _MCU_CLOCK_SYNC_RE.match(text)
                if m is None:
                    continue
                return _boot_wall_from_sync(
                    int(m.group("tick")), int(m.group("epoch_2020"))
                ), 0.95
    except OSError:
        return None
    return None


def detect_mcu_segments(file_path: Path) -> list[BootSegment]:
    """Walk the file once, splitting on tick resets (``tick < prev_tick``) and
    extracting per-segment boot wall-clock from the first ``Set Date By Second``
    line within each segment. Lines before the first valid ``&<tick>`` line are
    folded into segment 0; segments without any clock_sync remain unsynced.

    Each tick reset starts a new segment with its own boot wall-clock — MCU
    accumulates many boot sessions in one captured file."""
    segs: list[BootSegment] = []
    seq_no = 0
    cur_line_start = 0
    cur_byte_start = 0
    cur_first_sync: Optional[tuple[int, int]] = None  # (tick_ms, epoch_2020)
    cur_raw_min: Optional[float] = None
    cur_raw_max: Optional[float] = None
    prev_tick: Optional[int] = None

    line_no = 0
    byte_offset = 0

    def _flush(end_line: int, end_byte: int) -> None:
        nonlocal seq_no, cur_first_sync, cur_raw_min, cur_raw_max
        if end_line == cur_line_start:
            return  # empty segment, skip
        clock_offset: Optional[float] = None
        conf = 0.0
        if cur_first_sync is not None:
            clock_offset = _boot_wall_from_sync(*cur_first_sync)
            conf = 0.95
        segs.append(
            BootSegment(
                seq_no=seq_no,
                line_start=cur_line_start,
                line_end=end_line,
                byte_start=cur_byte_start,
                byte_end=end_byte,
                raw_ts_min=cur_raw_min,
                raw_ts_max=cur_raw_max,
                clock_offset=clock_offset,
                offset_confidence=conf,
            )
        )
        seq_no += 1
        cur_first_sync = None
        cur_raw_min = None
        cur_raw_max = None

    with open(file_path, "rb") as f:
        for raw in f:
            text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            m = _MCU_TICK_RE.match(text)
            if m is not None:
                tick = int(m.group("tick"))
                if prev_tick is not None and tick < prev_tick:
                    _flush(line_no, byte_offset)
                    cur_line_start = line_no
                    cur_byte_start = byte_offset
                ts = tick / 1000.0
                cur_raw_min = ts if cur_raw_min is None or ts < cur_raw_min else cur_raw_min
                cur_raw_max = ts if cur_raw_max is None or ts > cur_raw_max else cur_raw_max
                prev_tick = tick
                if cur_first_sync is None:
                    sm = _MCU_CLOCK_SYNC_RE.match(text)
                    if sm is not None:
                        cur_first_sync = (
                            int(sm.group("tick")),
                            int(sm.group("epoch_2020")),
                        )
            byte_offset += len(raw)
            line_no += 1

    _flush(line_no, byte_offset)
    return segs


class McuTickDecoder(BaseDecoder):
    """MCU log: ``&<tick_ms> <SEV>@<MOD>:<msg>`` where tick is millis-since-boot.

    Text is already human-readable; we keep the file as-is on disk and only
    derive ``raw_timestamp = tick_ms / 1000`` per line. The boot wall-clock
    that turns those relative seconds into absolute time is read from
    ``Set Date By Second`` lines and applied as the file's ``clock_offset``
    via the decode stage (method = CLOCK_SYNC).
    """

    controller = ControllerType.MCU

    def can_decode(self, file_path: Path) -> bool:
        try:
            with open(file_path, "rb") as f:
                head = f.read(4096)
        except OSError:
            return False
        if head.count(b"\x00") > len(head) // 8:
            return False
        for raw in head.splitlines():
            line = raw.decode("utf-8", errors="replace")
            if not line.strip():
                continue
            return bool(_MCU_TICK_RE.match(line))
        return False

    def iter_lines(self, file_path: Path) -> Iterator[DecodedLine]:
        for line_no, byte_offset, text in iter_text_lines(file_path):
            ts = parse_mcu_tick(text)
            yield DecodedLine(line_no=line_no, byte_offset=byte_offset, raw_timestamp=ts, text=text)
