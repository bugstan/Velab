from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator, Literal, Optional, Protocol
from uuid import UUID


class ControllerType(str, Enum):
    ANDROID = "android"
    TBOX = "tbox"
    FOTA = "fota"
    MCU = "mcu"
    KERNEL = "kernel"
    IBDU = "ibdu"
    UNKNOWN = "unknown"


class AlignmentStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class AlignmentMethod(str, Enum):
    DIRECT = "direct"
    TWO_HOP = "two_hop"
    FILENAME_ANCHOR = "filename_anchor"
    CLOCK_SYNC = "clock_sync"
    SEGMENTED = "segmented"
    NONE = "none"


class BundleStatus(str, Enum):
    QUEUED = "queued"
    EXTRACTING = "extracting"
    DECODING = "decoding"
    PRESCANNING = "prescanning"
    ALIGNING = "aligning"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True)
class BootSegment:
    """Span of a multi-boot file representing one boot session.

    Used today by MCU logs (``&<tick_ms>`` resets at every reboot). Each segment
    has its own boot wall-clock derived from an in-band ``Set Date By Second``
    line; ``aligned_ts = raw_ts + clock_offset`` for lines in this segment.
    """

    seq_no: int
    line_start: int
    line_end: int
    byte_start: int
    byte_end: int
    raw_ts_min: Optional[float]
    raw_ts_max: Optional[float]
    clock_offset: Optional[float]
    offset_confidence: float


@dataclass(frozen=True)
class LogFileMeta:
    file_id: UUID
    bundle_id: UUID
    controller: ControllerType
    original_name: str
    """Basename only (last path segment), used for the on-disk filename suffix."""
    stored_path: str
    bundle_relative_path: str = ""
    """Full POSIX-style path of the file as it appeared inside the original bundle."""
    size_bytes: int = 0
    sha256: Optional[str] = None
    """Hex SHA-256 of the file's raw bytes — set by the extractor and used by
    the pipeline to skip duplicate copies (e.g. a file that exists both inside
    a nested archive and as a sibling already pre-extracted next to it)."""
    decoded_path: Optional[str] = None
    raw_ts_min: Optional[float] = None
    raw_ts_max: Optional[float] = None
    valid_ts_min: Optional[float] = None
    valid_ts_max: Optional[float] = None
    unsynced_line_ranges: tuple[tuple[int, int], ...] = ()
    line_count: int = 0
    bucket_index_path: Optional[str] = None
    clock_offset: Optional[float] = None
    offset_confidence: float = 0.0
    offset_method: AlignmentMethod = AlignmentMethod.NONE
    segments: tuple[BootSegment, ...] = ()
    """Non-empty when this file packs multiple boot sessions (offset_method=SEGMENTED).
    Each segment's ``clock_offset`` overrides the file-level one for lines in its
    line/byte range."""


@dataclass(frozen=True)
class AnchorCandidate:
    anchor_type: str
    controller: ControllerType
    raw_timestamp: float
    line_no: int
    confidence: float
    fields: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ImportantEvent:
    event_id: UUID
    bundle_id: UUID
    file_id: UUID
    controller: ControllerType
    event_type: str
    raw_timestamp: float
    aligned_timestamp: Optional[float]
    alignment_quality: float
    line_no: int
    raw_line: str
    extracted_fields: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SourceOffset:
    offset: Optional[float]
    confidence: float
    method: AlignmentMethod
    sample_count: int


@dataclass(frozen=True)
class BundleAlignmentSummary:
    status: AlignmentStatus
    base_clock: ControllerType
    sources: dict[ControllerType, SourceOffset]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecodedLine:
    line_no: int
    byte_offset: int
    raw_timestamp: Optional[float]
    text: str


class LogDecoder(Protocol):
    controller: ControllerType

    def can_decode(self, file_path: str) -> bool: ...

    def iter_lines(self, file_path: str) -> Iterator[DecodedLine]: ...

    def decoded_format(self) -> Literal["text", "ndjson"]: ...


MIN_VALID_TS: float = 1577836800.0
"""2020-01-01 00:00:00 UTC — timestamps below this are treated as unsynced."""

BUCKET_SECONDS: int = 300
"""5-minute bucket size for the file-level time index."""

MAX_OFFSET_SECONDS: float = 30 * 86400.0
"""Sanity ceiling: offsets larger than 30 days are treated as bogus."""

RAW_LINE_TRUNCATE_BYTES: int = 4096
"""Important events store at most 4 KB of the raw line."""
