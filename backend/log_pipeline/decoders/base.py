from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal, Optional

from log_pipeline.interfaces import ControllerType, DecodedLine

_FILENAME_DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-_]?(\d{2})[-_]?(\d{2})(?!\d)")


def infer_year_hint(file_path: Path) -> int:
    """Best-effort year for log lines whose timestamp lacks a year (e.g. logcat MM-DD).

    Order: filename date → file mtime → current year.
    """
    name = Path(file_path).name
    m = _FILENAME_DATE_RE.search(name)
    if m:
        return int(m.group(1))
    try:
        ts = Path(file_path).stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc).year
    except OSError:
        return datetime.now(tz=timezone.utc).year


def iter_text_lines(path: Path, encoding: str = "utf-8") -> Iterator[tuple[int, int, str]]:
    """Iterate ``(line_no, byte_offset, text)`` over a text file read in binary.

    Decodes each line with ``errors='replace'`` so a single bad byte never aborts
    the stream. Strips trailing CR/LF from the returned text but the byte_offset
    advances by the full raw line length (newline included).
    """
    offset = 0
    line_no = 0
    with open(path, "rb") as f:
        first = f.read(3)
        if first == b"\xef\xbb\xbf":
            offset = 3
        else:
            f.seek(0)
        for raw in f:
            text = raw.decode(encoding, errors="replace").rstrip("\r\n")
            yield line_no, offset, text
            offset += len(raw)
            line_no += 1


class BaseDecoder(ABC):
    """Abstract base — concrete decoders subclass and implement ``iter_lines``."""

    controller: ControllerType
    """Which controller type this decoder serves."""

    @abstractmethod
    def can_decode(self, file_path: Path) -> bool: ...

    @abstractmethod
    def iter_lines(self, file_path: Path) -> Iterator[DecodedLine]: ...

    def decoded_format(self) -> Literal["text", "ndjson"]:
        return "text"

    def writes_decoded_file(self) -> bool:
        """True for binary sources (DLT) that materialise a {stored_path}.decoded.log;
        False for text sources whose ``stored_path`` is already human-readable."""
        return False


class DecoderRegistry:
    """Picks the right decoder per (controller, file_path).

    Decoders are tried in registration order; the first ``can_decode`` wins.
    Registering more specific decoders before fallbacks is the caller's job.
    """

    def __init__(self) -> None:
        self._decoders: list[BaseDecoder] = []

    def register(self, decoder: BaseDecoder) -> None:
        self._decoders.append(decoder)

    def find(self, controller: ControllerType, file_path: Path) -> Optional[BaseDecoder]:
        for d in self._decoders:
            if d.controller != controller:
                continue
            try:
                if d.can_decode(file_path):
                    return d
            except OSError:
                continue
        return None

    def __iter__(self):
        return iter(self._decoders)


def default_registry() -> DecoderRegistry:
    """Build the registry with all built-in decoders in the right priority order."""
    from log_pipeline.decoders.android_logcat import AndroidLogcatDecoder
    from log_pipeline.decoders.dlt import DLTDecoder
    from log_pipeline.decoders.fota_text import FotaTextDecoder
    from log_pipeline.decoders.ibdu import IBDUDecoder
    from log_pipeline.decoders.kernel import KernelDmesgDecoder, KernelLogcatDecoder
    from log_pipeline.decoders.tbox_text import TboxTextDecoder
    from log_pipeline.decoders.mcu_text import McuTickDecoder

    reg = DecoderRegistry()
    # tbox: DLT must be tried before plain text fallback
    reg.register(DLTDecoder())
    reg.register(TboxTextDecoder())
    # kernel: dmesg first (very specific signature), logcat-style as fallback
    reg.register(KernelDmesgDecoder())
    reg.register(KernelLogcatDecoder())
    # the rest
    reg.register(AndroidLogcatDecoder())
    reg.register(FotaTextDecoder())
    reg.register(IBDUDecoder())
    reg.register(McuTickDecoder())
    return reg
