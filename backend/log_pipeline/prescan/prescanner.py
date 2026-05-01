from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional
from uuid import UUID

from log_pipeline.decoders.base import BaseDecoder, DecoderRegistry, iter_text_lines
from log_pipeline.index.file_index import BucketIndexWriter
from log_pipeline.interfaces import (
    AlignmentMethod,
    AnchorCandidate,
    BootSegment,
    ControllerType,
    DecodedLine,
    ImportantEvent,
    LogFileMeta,
    is_effective_wall_clock_ts,
)
from log_pipeline.prescan.rule_engine import RuleEngine

logger = logging.getLogger(__name__)

_DLT_DECODED_TS_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d{1,9})"
)


def _segment_for_line(
    segments: tuple[BootSegment, ...], line_no: int, ptr: list[int]
) -> Optional[BootSegment]:
    """Walk forward through the (line-ordered) segment list to find the one
    containing ``line_no``. ``ptr`` is a 1-element list shared across calls so
    successive forward-only lookups stay O(1) amortised."""
    while ptr[0] < len(segments) and segments[ptr[0]].line_end <= line_no:
        ptr[0] += 1
    if ptr[0] >= len(segments):
        return None
    seg = segments[ptr[0]]
    if seg.line_start <= line_no < seg.line_end:
        return seg
    return None


def parse_dlt_decoded_timestamp(text: str) -> Optional[float]:
    """Parse the ISO timestamp prefix produced by ``DLTDecoder``."""
    m = _DLT_DECODED_TS_RE.match(text)
    if not m:
        return None
    try:
        date = datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    h, mn, s = int(m.group(2)), int(m.group(3)), int(m.group(4))
    if h >= 24 or mn >= 60 or s >= 60:
        return None
    frac_str = m.group(5)
    frac = int(frac_str) / (10 ** len(frac_str))
    return date.timestamp() + h * 3600 + mn * 60 + s + frac


def iter_dlt_decoded_log(path: Path) -> Iterator[DecodedLine]:
    """Replay a previously-decoded DLT text file as DecodedLine records."""
    for line_no, byte_offset, text in iter_text_lines(path):
        ts = parse_dlt_decoded_timestamp(text)
        yield DecodedLine(line_no=line_no, byte_offset=byte_offset, raw_timestamp=ts, text=text)


@dataclass
class PrescanResult:
    file_id: UUID
    line_count: int = 0
    raw_ts_min: Optional[float] = None
    raw_ts_max: Optional[float] = None
    valid_ts_min: Optional[float] = None
    valid_ts_max: Optional[float] = None
    unsynced_line_ranges: list[tuple[int, int]] = field(default_factory=list)
    bucket_index_path: Optional[str] = None
    bucket_record_count: int = 0
    events: list[ImportantEvent] = field(default_factory=list)
    anchors: list[AnchorCandidate] = field(default_factory=list)


class Prescanner:
    """Single-pass pre-scanner per file. Stateless across files; safe to reuse."""

    def __init__(self, registry: DecoderRegistry, rule_engine: RuleEngine):
        self._registry = registry
        self._rules = rule_engine

    def run_file(self, meta: LogFileMeta, index_dir: Path) -> Optional[PrescanResult]:
        if meta.decoded_path is None:
            return None
        decoded_path = Path(meta.decoded_path)
        if not decoded_path.is_file():
            return None

        is_dlt_replay = meta.decoded_path != meta.stored_path
        line_iter = self._line_iterator(meta, decoded_path, is_dlt_replay)
        if line_iter is None:
            return None

        result = PrescanResult(file_id=meta.file_id)
        idx_path = index_dir / f"{meta.file_id}.idx"
        unsynced_start: Optional[int] = None
        prev_line_no = -1
        ranges: list[tuple[int, int]] = []

        # Files whose per-file offset was set in advance (kernel_logs boot
        # captures, kernel/ runtime dumps, MCU clock_sync) carry boot-relative
        # raw_ts but are *already* alignable — every line is "valid" and
        # contributes to the bucket index. The index stores raw_ts unchanged
        # so the query path's symmetric ``raw_start = aligned_start - offset``
        # lookup keeps working.
        is_pre_aligned = (
            meta.clock_offset is not None
            and meta.offset_method
            in (AlignmentMethod.FILENAME_ANCHOR, AlignmentMethod.CLOCK_SYNC)
        )
        is_segmented = meta.offset_method == AlignmentMethod.SEGMENTED and meta.segments

        if is_pre_aligned:
            self._emit_boot_session_event(meta, result)

        # Segmented files (multi-boot MCU): different valid_ts semantics — we
        # compute min/max in *aligned* space (raw + segment.clock_offset) and
        # skip the bucket index since raw_ts is non-monotonic across segments.
        seg_ptr = [0] if is_segmented else None

        with BucketIndexWriter(idx_path) as idx:
            for ln in line_iter:
                result.line_count += 1
                ts = ln.raw_timestamp
                # raw range
                if ts is not None:
                    result.raw_ts_min = ts if result.raw_ts_min is None or ts < result.raw_ts_min else result.raw_ts_min
                    result.raw_ts_max = ts if result.raw_ts_max is None or ts > result.raw_ts_max else result.raw_ts_max

                if is_segmented:
                    seg = _segment_for_line(meta.segments, ln.line_no, seg_ptr)  # type: ignore[arg-type]
                    aligned_ts: Optional[float] = (
                        ts + seg.clock_offset
                        if (ts is not None and seg is not None and seg.clock_offset is not None)
                        else None
                    )
                    if is_effective_wall_clock_ts(aligned_ts):
                        if result.valid_ts_min is None or aligned_ts < result.valid_ts_min:
                            result.valid_ts_min = aligned_ts
                        if result.valid_ts_max is None or aligned_ts > result.valid_ts_max:
                            result.valid_ts_max = aligned_ts
                        if unsynced_start is not None:
                            ranges.append((unsynced_start, prev_line_no))
                            unsynced_start = None
                    else:
                        if unsynced_start is None:
                            unsynced_start = ln.line_no
                else:
                    aligned_candidate = (
                        ts + float(meta.clock_offset)
                        if (is_pre_aligned and ts is not None)
                        else ts
                    )
                    if ts is not None and is_effective_wall_clock_ts(aligned_candidate):
                        if result.valid_ts_min is None or ts < result.valid_ts_min:
                            result.valid_ts_min = ts
                        if result.valid_ts_max is None or ts > result.valid_ts_max:
                            result.valid_ts_max = ts
                        idx.append(ts, ln.byte_offset, ln.line_no)
                        if unsynced_start is not None:
                            ranges.append((unsynced_start, prev_line_no))
                            unsynced_start = None
                    else:
                        if unsynced_start is None:
                            unsynced_start = ln.line_no
                prev_line_no = ln.line_no

                if ln.text:
                    self._apply_rules(meta, ln, result)

            if unsynced_start is not None:
                ranges.append((unsynced_start, prev_line_no))
            result.unsynced_line_ranges = ranges
            result.bucket_record_count = idx.records_written

        if is_segmented:
            # discard the (necessarily empty / non-monotonic) bucket file
            try:
                Path(idx_path).unlink(missing_ok=True)
            except OSError:
                pass
            result.bucket_index_path = None
            self._apply_segment_offsets_to_events(result, meta)
        else:
            result.bucket_index_path = str(idx_path)
            # Backfill aligned_timestamp on every event from a pre-aligned file.
            # Cheaper than threading the offset through ``_apply_rules`` and keeps
            # that hot path uniform across decoders.
            if is_pre_aligned:
                self._apply_offset_to_events(result, float(meta.clock_offset))  # type: ignore[arg-type]

        return result

    def _emit_boot_session_event(self, meta: LogFileMeta, out: PrescanResult) -> None:
        """One synthetic event per boot capture, stamped at the filename's wall clock.
        Only emitted for ``kernel_logs/`` dmesg snapshots — runtime ringbuffer
        dumps in ``kernel/`` share the FILENAME_ANCHOR offset method but are
        not per-boot events, so they get no synthetic marker."""
        if meta.clock_offset is None:
            return
        if "/kernel_logs/" not in meta.bundle_relative_path.replace("\\", "/"):
            return
        out.events.append(
            ImportantEvent(
                event_id=uuid.uuid4(),
                bundle_id=meta.bundle_id,
                file_id=meta.file_id,
                controller=meta.controller,
                event_type="boot_session",
                raw_timestamp=0.0,
                aligned_timestamp=float(meta.clock_offset),
                alignment_quality=0.99,
                line_no=0,
                raw_line=meta.original_name,
                extracted_fields={
                    "source": "kernel_logs",
                    "filename": meta.original_name,
                    "bundle_relative_path": meta.bundle_relative_path,
                },
            )
        )

    @staticmethod
    def _apply_offset_to_events(result: PrescanResult, offset: float) -> None:
        """Replace each event with one carrying ``aligned_timestamp = raw + offset``.
        Skips the synthetic boot_session whose aligned_ts is already absolute."""
        rewritten: list[ImportantEvent] = []
        for ev in result.events:
            if ev.aligned_timestamp is not None:
                rewritten.append(ev)
                continue
            rewritten.append(
                ImportantEvent(
                    event_id=ev.event_id,
                    bundle_id=ev.bundle_id,
                    file_id=ev.file_id,
                    controller=ev.controller,
                    event_type=ev.event_type,
                    raw_timestamp=ev.raw_timestamp,
                    aligned_timestamp=ev.raw_timestamp + offset,
                    alignment_quality=0.99,
                    line_no=ev.line_no,
                    raw_line=ev.raw_line,
                    extracted_fields=ev.extracted_fields,
                )
            )
        result.events = rewritten

    @staticmethod
    def _apply_segment_offsets_to_events(result: PrescanResult, meta: LogFileMeta) -> None:
        """Look up each event's segment by line_no and stamp aligned_timestamp
        from that segment's clock_offset. Events in a segment without a
        clock_sync line stay aligned=None (= file's unsynced range)."""
        if not meta.segments:
            return
        seg_ptr = [0]
        # events are emitted in line_no order during the single-pass scan
        rewritten: list[ImportantEvent] = []
        for ev in result.events:
            if ev.aligned_timestamp is not None:
                rewritten.append(ev)
                continue
            seg = _segment_for_line(meta.segments, ev.line_no, seg_ptr)
            if seg is None or seg.clock_offset is None:
                rewritten.append(ev)
                continue
            rewritten.append(
                ImportantEvent(
                    event_id=ev.event_id,
                    bundle_id=ev.bundle_id,
                    file_id=ev.file_id,
                    controller=ev.controller,
                    event_type=ev.event_type,
                    raw_timestamp=ev.raw_timestamp,
                    aligned_timestamp=ev.raw_timestamp + seg.clock_offset,
                    alignment_quality=seg.offset_confidence,
                    line_no=ev.line_no,
                    raw_line=ev.raw_line,
                    extracted_fields=ev.extracted_fields,
                )
            )
        result.events = rewritten

    def _line_iterator(
        self, meta: LogFileMeta, decoded_path: Path, is_dlt_replay: bool
    ) -> Optional[Iterator[DecodedLine]]:
        if is_dlt_replay:
            return iter_dlt_decoded_log(decoded_path)
        decoder: Optional[BaseDecoder] = self._registry.find(meta.controller, decoded_path)
        if decoder is None:
            return None
        return decoder.iter_lines(decoded_path)

    def _apply_rules(self, meta: LogFileMeta, ln: DecodedLine, out: PrescanResult) -> None:
        for hit in self._rules.match(meta.controller, ln.text):
            if hit.rule_kind == "event":
                out.events.append(
                    ImportantEvent(
                        event_id=uuid.uuid4(),
                        bundle_id=meta.bundle_id,
                        file_id=meta.file_id,
                        controller=meta.controller,
                        event_type=hit.rule_type,
                        raw_timestamp=ln.raw_timestamp if ln.raw_timestamp is not None else 0.0,
                        aligned_timestamp=None,
                        alignment_quality=0.0,
                        line_no=ln.line_no,
                        raw_line=ln.text,
                        extracted_fields=hit.fields,
                    )
                )
            else:  # anchor
                out.anchors.append(
                    AnchorCandidate(
                        anchor_type=hit.rule_type,
                        controller=meta.controller,
                        raw_timestamp=ln.raw_timestamp if ln.raw_timestamp is not None else 0.0,
                        line_no=ln.line_no,
                        confidence=hit.confidence,
                        fields=hit.fields,
                    )
                )
