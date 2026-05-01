from __future__ import annotations

import logging
import multiprocessing as mp
import os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Callable, Optional
from uuid import UUID

from log_pipeline.decoders.base import DecoderRegistry, default_registry
from log_pipeline.interfaces import LogFileMeta
from log_pipeline.prescan.prescanner import PrescanResult, Prescanner
from log_pipeline.prescan.rule_engine import RuleEngine
from log_pipeline.storage.catalog import Catalog
from log_pipeline.storage.eventdb import EventDB
from log_pipeline.storage.filestore import FileStore

logger = logging.getLogger(__name__)

_PARALLEL_MIN_FILES = 4
"""Below this many files spawning workers is slower than the work itself."""

# Per-worker cached state — keyed by os.getpid() doesn't matter since each worker
# has its own module instance. The ProcessPoolExecutor `initializer` populates these.
_W_REGISTRY: Optional[DecoderRegistry] = None
_W_RULES: Optional[RuleEngine] = None


def _init_worker(event_yaml: str, anchor_yaml: str) -> None:
    global _W_REGISTRY, _W_RULES
    _W_REGISTRY = default_registry()
    _W_RULES = RuleEngine.from_yaml_files(Path(event_yaml), Path(anchor_yaml))


def _prescan_one_worker(args: tuple[LogFileMeta, str]) -> Optional[PrescanResult]:
    meta, index_dir = args
    assert _W_REGISTRY is not None and _W_RULES is not None
    return Prescanner(_W_REGISTRY, _W_RULES).run_file(meta, Path(index_dir))


class PrescanStage:
    """Stage 5: prescan — events + anchors + bucket index + unsynced ranges.

    Files are pre-scanned in parallel via a ``ProcessPoolExecutor`` (one worker
    per CPU by default). The main process drains results in submission order
    and serialises catalog + eventdb updates (SQLite tolerates concurrent reads
    but only one writer).
    """

    def __init__(
        self,
        registry: DecoderRegistry,
        rule_engine: RuleEngine,
        catalog: Catalog,
        eventdb: EventDB,
        filestore: FileStore,
        index_root: Path,
        event_rules_yaml: Optional[Path] = None,
        anchor_rules_yaml: Optional[Path] = None,
        max_workers: int = 0,
    ):
        self._registry = registry
        self._rules = rule_engine
        self._catalog = catalog
        self._eventdb = eventdb
        self._filestore = filestore
        self._index_root = Path(index_root)
        self._event_yaml = event_rules_yaml
        self._anchor_yaml = anchor_rules_yaml
        self._max_workers = max_workers or (os.cpu_count() or 1)

    def run(
        self,
        bundle_id: UUID,
        progress_cb: Optional[Callable[[float], None]] = None,
    ) -> dict[str, int]:
        self._eventdb.clear_for_bundle(bundle_id)
        files = self._catalog.list_files_by_bundle(bundle_id)
        index_dir = self._index_root / str(bundle_id)
        index_dir.mkdir(parents=True, exist_ok=True)

        if (
            self._max_workers <= 1
            or len(files) < _PARALLEL_MIN_FILES
            or self._event_yaml is None
            or self._anchor_yaml is None
        ):
            results = self._scan_sequential(files, index_dir, progress_cb)
        else:
            results = self._scan_parallel(files, index_dir, progress_cb)

        return self._persist_results(bundle_id, files, results)

    def _scan_sequential(
        self,
        files: list[LogFileMeta],
        index_dir: Path,
        progress_cb: Optional[Callable[[float], None]],
    ) -> list[Optional[PrescanResult]]:
        prescanner = Prescanner(self._registry, self._rules)
        total = len(files)
        out: list[Optional[PrescanResult]] = []
        for i, m in enumerate(files):
            out.append(prescanner.run_file(m, index_dir))
            if progress_cb is not None and total:
                progress_cb((i + 1) / total)
        return out

    def _scan_parallel(
        self,
        files: list[LogFileMeta],
        index_dir: Path,
        progress_cb: Optional[Callable[[float], None]],
    ) -> list[Optional[PrescanResult]]:
        args = [(m, str(index_dir)) for m in files]
        total = len(args)
        # Use ``fork`` on POSIX so we inherit imports cheaply and don't have to
        # re-execute the launcher script (spawn breaks for stdin/heredoc launches
        # on macOS). Workload is CPU-bound regex matching with no shared mutable
        # state, so fork is safe here.
        ctx = mp.get_context("fork") if os.name == "posix" else mp.get_context()
        with ProcessPoolExecutor(
            max_workers=self._max_workers,
            mp_context=ctx,
            initializer=_init_worker,
            initargs=(str(self._event_yaml), str(self._anchor_yaml)),
        ) as pool:
            out: list[Optional[PrescanResult]] = []
            # pool.map preserves submission order; iterating lazily lets us tick
            # progress as each future resolves rather than waiting for the full
            # batch via list(...).
            for i, r in enumerate(pool.map(_prescan_one_worker, args, chunksize=1)):
                out.append(r)
                if progress_cb is not None and total:
                    progress_cb((i + 1) / total)
            return out

    def _persist_results(
        self,
        bundle_id: UUID,
        files: list[LogFileMeta],
        results: list[Optional[PrescanResult]],
    ) -> dict[str, int]:
        events_total = 0
        anchors_total = 0
        unsynced_files = 0
        files_indexed = 0
        skipped = 0
        per_event_type: Counter[str] = Counter()

        for meta, res in zip(files, results):
            if res is None:
                skipped += 1
                continue
            self._catalog.update_file_prescan_meta(
                file_id=meta.file_id,
                bucket_index_path=res.bucket_index_path,
                line_count=res.line_count,
                raw_ts_min=res.raw_ts_min,
                raw_ts_max=res.raw_ts_max,
                valid_ts_min=res.valid_ts_min,
                valid_ts_max=res.valid_ts_max,
                unsynced_line_ranges=res.unsynced_line_ranges,
            )
            if res.events:
                events_total += self._eventdb.insert_events_batch(res.events)
                for ev in res.events:
                    per_event_type[ev.event_type] += 1
            if res.anchors:
                anchors_total += self._eventdb.insert_anchors_batch(
                    bundle_id, meta.file_id, res.anchors
                )
            if res.unsynced_line_ranges:
                unsynced_files += 1
            if res.bucket_record_count > 0:
                files_indexed += 1

        self._filestore.append_processing_log(
            bundle_id,
            f"prescan events={events_total} anchors={anchors_total} "
            f"indexed_files={files_indexed} unsynced_files={unsynced_files} skipped={skipped} "
            f"per_event={dict(per_event_type)} workers={self._max_workers}",
        )
        return {
            "events": events_total,
            "anchors": anchors_total,
            "indexed_files": files_indexed,
            "unsynced_files": unsynced_files,
            "skipped": skipped,
            "workers": self._max_workers,
        }
