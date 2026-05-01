from __future__ import annotations

import logging
import shutil
from collections import Counter
from pathlib import Path
from typing import Callable
from uuid import UUID, uuid4

from log_pipeline.alignment.crash_heuristic import detect_suspected_crashes
from log_pipeline.alignment.stage import AlignStage
from log_pipeline.config import Settings
from log_pipeline.decoders.base import DecoderRegistry, default_registry
from log_pipeline.decoders.stage import DecodeStage
from log_pipeline.ingest.classifier import Classifier
from log_pipeline.ingest.extractor import Extractor
from log_pipeline.interfaces import BundleStatus, ControllerType
from log_pipeline.prescan.rule_engine import RuleEngine
from log_pipeline.prescan.stage import PrescanStage
from log_pipeline.storage.catalog import Catalog
from log_pipeline.storage.eventdb import EventDB
from log_pipeline.storage.filestore import FileStore

logger = logging.getLogger(__name__)


class IngestPipeline:
    """M1 pipeline: extract → classify → store → catalog.

    Decode / prescan / alignment / events are added in M2–M4.
    """

    def __init__(
        self,
        settings: Settings,
        catalog: Catalog,
        filestore: FileStore,
        classifier: Classifier,
        eventdb: EventDB | None = None,
        rule_engine: RuleEngine | None = None,
        decoder_registry: DecoderRegistry | None = None,
    ):
        self._settings = settings
        self._catalog = catalog
        self._filestore = filestore
        self._classifier = classifier
        self._decoder_registry = decoder_registry or default_registry()
        self._decode_stage = DecodeStage(self._decoder_registry, catalog, filestore)
        self._eventdb = eventdb or EventDB(settings.catalog_db)
        self._rule_engine = rule_engine or RuleEngine.from_yaml_files(
            settings.event_rules_yaml, settings.anchor_rules_yaml
        )
        self._prescan_stage = PrescanStage(
            self._decoder_registry,
            self._rule_engine,
            catalog,
            self._eventdb,
            filestore,
            settings.index_root,
            event_rules_yaml=settings.event_rules_yaml,
            anchor_rules_yaml=settings.anchor_rules_yaml,
        )
        self._align_stage = AlignStage(catalog, self._eventdb, filestore)

    def register_upload(self, archive_path: Path, archive_filename: str) -> UUID:
        bundle_id = uuid4()
        size = archive_path.stat().st_size if archive_path.exists() else None
        self._catalog.create_bundle(bundle_id, archive_filename, size)
        self._filestore.init_bundle(bundle_id)
        self._filestore.append_processing_log(
            bundle_id, f"upload archive={archive_filename!r} size={size}"
        )
        return bundle_id

    def run(self, bundle_id: UUID, archive_path: Path) -> dict:
        self._catalog.update_bundle_status(bundle_id, BundleStatus.EXTRACTING, progress=0.05)
        extractor = Extractor(work_root=self._settings.work_root)
        counts: Counter[str] = Counter()
        total_files = 0
        # Per-bundle dedup table: same hash from a different relative_path means
        # the same content was packed twice (e.g. someone pre-expanded a nested
        # archive next to its still-archived sibling). Keep the first, drop the
        # rest — and log it so the audit trail makes the dedup explicit.
        seen_hashes: dict[str, str] = {}
        dup_count = 0
        try:
            with self._filestore.processing_log(bundle_id, "extract+classify+store"):
                for ext in extractor.extract(archive_path):
                    if ext.sha256 in seen_hashes:
                        dup_count += 1
                        self._filestore.append_processing_log(
                            bundle_id,
                            f"dedup_skip path={ext.relative_path!r} "
                            f"sha256={ext.sha256[:12]}.. "
                            f"first_seen={seen_hashes[ext.sha256]!r}",
                        )
                        try:
                            ext.temp_path.unlink(missing_ok=True)
                        except OSError:
                            pass
                        continue
                    seen_hashes[ext.sha256] = ext.relative_path

                    controller = self._classifier.classify(ext.relative_path, ext.temp_path)
                    if controller == ControllerType.UNKNOWN:
                        self._filestore.append_processing_log(
                            bundle_id,
                            f"classify=UNKNOWN path={ext.relative_path!r}",
                        )
                    meta = self._filestore.store_file(
                        bundle_id, controller, ext.relative_path, ext.temp_path,
                        sha256=ext.sha256,
                    )
                    self._catalog.insert_file_meta(meta)
                    counts[controller.value] += 1
                    total_files += 1
            self._catalog.update_bundle_status(bundle_id, BundleStatus.DECODING, progress=0.4)
            with self._filestore.processing_log(bundle_id, "decode"):
                decode_counts = self._decode_stage.run(
                    bundle_id,
                    progress_cb=self._make_progress_cb(
                        bundle_id, BundleStatus.DECODING, 0.4, 0.7
                    ),
                )
            self._filestore.append_processing_log(
                bundle_id, f"decode counts={decode_counts}"
            )
            self._catalog.update_bundle_status(bundle_id, BundleStatus.PRESCANNING, progress=0.7)
            with self._filestore.processing_log(bundle_id, "prescan"):
                prescan_counts = self._prescan_stage.run(
                    bundle_id,
                    progress_cb=self._make_progress_cb(
                        bundle_id, BundleStatus.PRESCANNING, 0.7, 0.9
                    ),
                )
            self._catalog.update_bundle_status(bundle_id, BundleStatus.ALIGNING, progress=0.9)
            with self._filestore.processing_log(bundle_id, "align"):
                align_summary = self._align_stage.run(bundle_id)
            with self._filestore.processing_log(bundle_id, "crash_heuristic"):
                n_crash = detect_suspected_crashes(bundle_id, self._catalog, self._eventdb)
            self._filestore.append_processing_log(
                bundle_id, f"crash_heuristic suspected={n_crash}"
            )
            self._catalog.update_bundle_status(bundle_id, BundleStatus.DONE, progress=1.0)
            summary = dict(counts)
            self._filestore.append_processing_log(
                bundle_id,
                f"ingest done total_files={total_files} dedup_skipped={dup_count} "
                f"per_controller={summary}",
            )
            return {
                "total_files": total_files,
                "dedup_skipped": dup_count,
                "per_controller": summary,
                "decode_counts": decode_counts,
                "prescan_counts": prescan_counts,
                "alignment": align_summary,
            }
        except Exception as e:
            logger.exception("ingest failed for bundle %s", bundle_id)
            self._catalog.update_bundle_status(
                bundle_id, BundleStatus.FAILED, error=f"{type(e).__name__}: {e}"
            )
            raise
        finally:
            self._cleanup_work_dirs()

    def _make_progress_cb(
        self,
        bundle_id: UUID,
        status: BundleStatus,
        start: float,
        end: float,
    ) -> Callable[[float], None]:
        """Build a sub-stage progress reporter that maps ratio∈[0,1] into the
        global ``[start, end]`` band and writes back via catalog. Throttled to
        ≥1% delta so a 1000-file decode doesn't fire 1000 SQLite UPDATEs."""
        span = end - start
        last = [start]

        def cb(ratio: float) -> None:
            ratio = 0.0 if ratio < 0.0 else 1.0 if ratio > 1.0 else ratio
            value = start + span * ratio
            if value - last[0] < 0.01 and ratio < 1.0:
                return
            last[0] = value
            self._catalog.update_bundle_status(bundle_id, status, progress=value)

        return cb

    def _cleanup_work_dirs(self) -> None:
        for d in self._settings.work_root.iterdir() if self._settings.work_root.exists() else []:
            if d.is_dir() and d.name.startswith("extract_"):
                shutil.rmtree(d, ignore_errors=True)
