from __future__ import annotations

import logging
import multiprocessing as mp
import os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from uuid import UUID

from log_pipeline.decoders.base import DecoderRegistry, default_registry
from log_pipeline.decoders.kernel import is_boot_capture_path, parse_kernel_dump_filename
from log_pipeline.decoders.mcu_text import detect_mcu_segments
from log_pipeline.interfaces import (
    AlignmentMethod,
    ControllerType,
    LogFileMeta,
    is_effective_wall_clock_ts,
)
from log_pipeline.storage.catalog import Catalog
from log_pipeline.storage.filestore import FileStore

logger = logging.getLogger(__name__)

_DECODED_SUFFIX = ".decoded.log"
_PARALLEL_MIN_FILES = 4
_W_REGISTRY: Optional[DecoderRegistry] = None


def _init_worker() -> None:
    global _W_REGISTRY
    _W_REGISTRY = default_registry()


def _decode_one_worker(meta: LogFileMeta) -> Optional[DecodeFileResult]:
    assert _W_REGISTRY is not None
    return _decode_one_impl(_W_REGISTRY, meta)


@dataclass
class DecodeFileResult:
    file_id: UUID
    controller: ControllerType
    decoder_name: str
    decoded_path: Optional[str]
    line_count: int
    raw_ts_min: Optional[float]
    raw_ts_max: Optional[float]
    valid_ts_min: Optional[float]
    valid_ts_max: Optional[float]
    bytes_written: int = 0


class DecodeStage:
    """Stage 4: per-file decoding.

    For binary sources (DLT) we materialise a ``{stored_path}.decoded.log`` text file
    and record its path in catalog. For text sources we don't rewrite — ``decoded_path``
    points at the original ``stored_path`` so downstream prescan can uniformly read it.
    """

    def __init__(
        self,
        registry: DecoderRegistry,
        catalog: Catalog,
        filestore: FileStore,
        max_workers: int = 0,
    ):
        self._registry = registry
        self._catalog = catalog
        self._filestore = filestore
        self._max_workers = max_workers or (os.cpu_count() or 1)

    def run(
        self,
        bundle_id: UUID,
        progress_cb: Optional[Callable[[float], None]] = None,
    ) -> dict[str, int]:
        files = self._catalog.list_files_by_bundle(bundle_id)
        counts: Counter[str] = Counter()
        total = len(files)
        results = self._decode_all(files, progress_cb)
        for meta, res in zip(files, results):
            if res is None:
                counts["unhandled"] += 1
                self._filestore.append_processing_log(
                    bundle_id,
                    f"decode SKIP file_id={meta.file_id} controller={meta.controller.value} "
                    f"path={meta.bundle_relative_path!r} (no decoder)",
                )
            else:
                self._catalog.update_file_decoded_meta(
                    file_id=res.file_id,
                    decoded_path=res.decoded_path,
                    line_count=res.line_count,
                    raw_ts_min=res.raw_ts_min,
                    raw_ts_max=res.raw_ts_max,
                    valid_ts_min=res.valid_ts_min,
                    valid_ts_max=res.valid_ts_max,
                )
                self._maybe_apply_filename_anchor(meta, res, bundle_id)
                counts[res.decoder_name] += 1
        return dict(counts)

    def _decode_all(
        self,
        files: list[LogFileMeta],
        progress_cb: Optional[Callable[[float], None]],
    ) -> list[Optional[DecodeFileResult]]:
        total = len(files)
        if (
            self._max_workers <= 1
            or total < _PARALLEL_MIN_FILES
        ):
            out: list[Optional[DecodeFileResult]] = []
            for i, meta in enumerate(files):
                out.append(self._decode_one(meta))
                if progress_cb is not None and total:
                    progress_cb((i + 1) / total)
            return out

        ctx = mp.get_context("fork") if os.name == "posix" else mp.get_context()
        with ProcessPoolExecutor(
            max_workers=self._max_workers,
            mp_context=ctx,
            initializer=_init_worker,
        ) as pool:
            out = []
            for i, res in enumerate(pool.map(_decode_one_worker, files, chunksize=1)):
                out.append(res)
                if progress_cb is not None and total:
                    progress_cb((i + 1) / total)
            return out

    def _maybe_apply_filename_anchor(
        self, meta: LogFileMeta, res: DecodeFileResult, bundle_id: UUID
    ) -> None:
        """Set ``clock_offset`` per-file when the file itself carries a
        wall-clock anchor — bypassing the controller-level direct/two-hop
        alignment that has nothing to anchor onto.

        Three flavours:
          * **kernel boot capture** (``kernel_logs/NNN_YYYY-MM-DD_HH-MM-SS.log``):
            dmesg relative seconds; the filename time is the boot wall-clock,
            so ``offset = boot_epoch``.
          * **kernel runtime dump** (``kernel/kernel@YYYY-...log``): pre-NTP
            ``01-01 HH:MM:SS`` content; the filename records dump time, so we
            anchor the latest entry to that wall-clock:
            ``offset = filename_epoch - raw_ts_max``.
          * **MCU clock_sync** (``mcu/MCU_*.txt``): tick is millis-since-boot;
            an in-band ``Set Date By Second: <epoch_2020>, ...`` line gives us
            the boot wall-clock directly. method=CLOCK_SYNC.
        """
        if meta.controller == ControllerType.KERNEL:
            self._apply_kernel_anchor(meta, res, bundle_id)
            return
        if meta.controller == ControllerType.MCU:
            self._apply_mcu_clock_sync(meta, bundle_id)
            return
        if meta.controller == ControllerType.IBDU:
            # iBDU lines carry absolute wall-clock in-band — offset is 0.
            # Recording it explicitly (instead of NULL) opts the file into the
            # windowed query path; without this it would only be reachable
            # via include_unsynced=true.
            if res.valid_ts_min is not None:
                self._write_offset(
                    meta, bundle_id, 0.0,
                    method=AlignmentMethod.CLOCK_SYNC, confidence=1.0,
                    tag="native (in-band wall-clock)",
                )
            return
        if meta.controller == ControllerType.TBOX:
            # tbox files (DLT decoded → ISO-prefixed ``.decoded.log`` and plain
            # text activelogs) carry absolute wall-clock; opt them into the
            # windowed query path the same way iBDU does. The bundle-level
            # alignment summary may still mark tbox=none (no anchor pairs to
            # *other* sources), but the per-file offset=0 is correct for
            # per-controller queries.
            if res.valid_ts_min is not None:
                self._write_offset(
                    meta, bundle_id, 0.0,
                    method=AlignmentMethod.CLOCK_SYNC, confidence=1.0,
                    tag="native (in-band wall-clock)",
                )
            return

    def _apply_kernel_anchor(
        self, meta: LogFileMeta, res: DecodeFileResult, bundle_id: UUID
    ) -> None:
        hit = is_boot_capture_path(meta.bundle_relative_path, meta.original_name)
        if hit is not None:
            _, boot_epoch = hit
            self._write_offset(
                meta, bundle_id, boot_epoch,
                method=AlignmentMethod.FILENAME_ANCHOR, confidence=0.99,
                tag=f"boot_epoch={boot_epoch:.0f}",
            )
            return
        dump_epoch = parse_kernel_dump_filename(meta.original_name)
        if dump_epoch is None or res.raw_ts_max is None:
            return
        offset = dump_epoch - res.raw_ts_max
        self._write_offset(
            meta, bundle_id, offset,
            method=AlignmentMethod.FILENAME_ANCHOR, confidence=0.85,
            tag=f"dump_epoch={dump_epoch:.0f} raw_ts_max={res.raw_ts_max:.0f}",
        )

    def _apply_mcu_clock_sync(self, meta: LogFileMeta, bundle_id: UUID) -> None:
        """Split the file into per-boot segments and persist them. Each segment
        has its own ``Set Date By Second``-derived boot wall-clock; the file
        itself becomes ``offset_method=SEGMENTED`` with NULL ``clock_offset``
        so the query path knows to consult ``segments`` instead."""
        segs = detect_mcu_segments(Path(meta.stored_path))
        if not segs:
            return
        aligned = sum(1 for s in segs if s.clock_offset is not None)
        self._catalog.update_file_segments(
            meta.file_id, segs, offset_method=AlignmentMethod.SEGMENTED.value
        )
        self._filestore.append_processing_log(
            bundle_id,
            f"segmented file_id={meta.file_id} segments={len(segs)} "
            f"aligned={aligned}/{len(segs)} path={meta.bundle_relative_path!r}",
        )

    def _write_offset(
        self,
        meta: LogFileMeta,
        bundle_id: UUID,
        offset: float,
        method: AlignmentMethod,
        confidence: float,
        tag: str,
    ) -> None:
        self._catalog.update_file_clock_offset(
            file_id=meta.file_id,
            clock_offset=offset,
            offset_confidence=confidence,
            offset_method=method.value,
        )
        self._filestore.append_processing_log(
            bundle_id,
            f"{method.value} file_id={meta.file_id} offset={offset:.3f} "
            f"conf={confidence} {tag} path={meta.bundle_relative_path!r}",
        )

    def _decode_one(self, meta: LogFileMeta) -> Optional[DecodeFileResult]:
        return _decode_one_impl(self._registry, meta)


def _decode_one_impl(
    registry: DecoderRegistry,
    meta: LogFileMeta,
) -> Optional[DecodeFileResult]:
    stored = Path(meta.stored_path)
    if not stored.is_file():
        return None
    decoder = registry.find(meta.controller, stored)
    if decoder is None:
        return None

    line_count = 0
    raw_min: Optional[float] = None
    raw_max: Optional[float] = None
    valid_min: Optional[float] = None
    valid_max: Optional[float] = None
    bytes_written = 0
    decoded_path: Optional[str] = None

    if decoder.writes_decoded_file():
        decoded_path = str(stored) + _DECODED_SUFFIX
        partial = decoded_path + ".partial"
        with open(partial, "w", encoding="utf-8") as out:
            for ln in decoder.iter_lines(stored):
                out.write(ln.text + "\n")
                line_count += 1
                bytes_written += len(ln.text) + 1
                raw_min, raw_max = _update_ts(ln.raw_timestamp, raw_min, raw_max)
                valid_min, valid_max = _update_valid(ln.raw_timestamp, valid_min, valid_max)
        Path(partial).replace(decoded_path)
    else:
        decoded_path = meta.stored_path
        for ln in decoder.iter_lines(stored):
            line_count += 1
            raw_min, raw_max = _update_ts(ln.raw_timestamp, raw_min, raw_max)
            valid_min, valid_max = _update_valid(ln.raw_timestamp, valid_min, valid_max)

    return DecodeFileResult(
        file_id=meta.file_id,
        controller=meta.controller,
        decoder_name=type(decoder).__name__,
        decoded_path=decoded_path,
        line_count=line_count,
        raw_ts_min=raw_min,
        raw_ts_max=raw_max,
        valid_ts_min=valid_min,
        valid_ts_max=valid_max,
        bytes_written=bytes_written,
    )


def _update_ts(
    ts: Optional[float], cur_min: Optional[float], cur_max: Optional[float]
) -> tuple[Optional[float], Optional[float]]:
    if ts is None:
        return cur_min, cur_max
    return (
        ts if cur_min is None or ts < cur_min else cur_min,
        ts if cur_max is None or ts > cur_max else cur_max,
    )


def _update_valid(
    ts: Optional[float], cur_min: Optional[float], cur_max: Optional[float]
) -> tuple[Optional[float], Optional[float]]:
    if not is_effective_wall_clock_ts(ts):
        return cur_min, cur_max
    return (
        ts if cur_min is None or ts < cur_min else cur_min,
        ts if cur_max is None or ts > cur_max else cur_max,
    )
