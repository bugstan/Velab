from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from log_pipeline.alignment.time_aligner import (
    align_bundle,
    to_anchor_view,
)
from log_pipeline.alignment.unsynced_segments import refine_with_clock_sync
from log_pipeline.interfaces import (
    AlignmentMethod,
    BundleAlignmentSummary,
    ControllerType,
)
from log_pipeline.storage.catalog import Catalog
from log_pipeline.storage.eventdb import EventDB
from log_pipeline.storage.filestore import FileStore

logger = logging.getLogger(__name__)


class AlignStage:
    """Stage 6: bundle-level alignment.

    Reads anchors per file from EventDB, computes per-controller offsets via
    direct + two-hop, refines unsynced ranges using ``tbox_clock_sync`` line
    numbers in mcu/kernel files, and writes results back to:
      - catalog: clock_offset / offset_confidence / offset_method / unsynced_ranges_json
      - bundles: alignment_summary_json
    """

    def __init__(self, catalog: Catalog, eventdb: EventDB, filestore: FileStore):
        self._catalog = catalog
        self._eventdb = eventdb
        self._filestore = filestore

    def run(self, bundle_id: UUID) -> dict:
        anchor_rows = self._eventdb.list_anchors(bundle_id)
        anchors = to_anchor_view(anchor_rows)

        files = self._catalog.list_files_by_bundle(bundle_id)
        controllers_present = sorted(
            {f.controller for f in files if f.controller != ControllerType.UNKNOWN},
            key=lambda c: c.value,
        )

        summary = align_bundle(anchors, controllers_present)
        self._apply_unsynced_refinement(bundle_id, anchor_rows, files)
        self._write_offsets_to_catalog(files, summary)
        self._write_summary_to_bundle(bundle_id, summary)
        sources_summary = {
            c.value: (o.method.value, round(o.confidence, 3))
            for c, o in summary.sources.items()
        }
        self._filestore.append_processing_log(
            bundle_id,
            f"alignment status={summary.status.value} base={summary.base_clock.value} "
            f"sources={sources_summary} warnings={list(summary.warnings)}",
        )
        return {
            "status": summary.status.value,
            "base_clock": summary.base_clock.value,
            "sources": {c.value: o.method.value for c, o in summary.sources.items()},
            "warnings": list(summary.warnings),
        }

    def _apply_unsynced_refinement(
        self, bundle_id: UUID, anchor_rows: list[dict], files: list
    ) -> None:
        """For mcu/kernel files: if a tbox_clock_sync anchor exists in that file, use its
        line_no to tighten the unsynced range to ``[(0, K-1)]``."""
        clock_sync_per_file: dict[str, int] = {}
        for r in anchor_rows:
            if r["anchor_type"] != "tbox_clock_sync":
                continue
            fid = r["file_id"]
            ln = r["line_no"]
            if fid not in clock_sync_per_file or ln < clock_sync_per_file[fid]:
                clock_sync_per_file[fid] = ln

        for meta in files:
            if meta.controller not in (ControllerType.MCU, ControllerType.KERNEL):
                continue
            if meta.offset_method in (
                AlignmentMethod.FILENAME_ANCHOR,
                AlignmentMethod.CLOCK_SYNC,
                AlignmentMethod.SEGMENTED,
            ):
                # already fully aligned per-file — don't second-guess unsynced.
                continue
            ln = clock_sync_per_file.get(str(meta.file_id))
            if ln is None:
                continue
            new_ranges = refine_with_clock_sync(list(meta.unsynced_line_ranges), ln)
            self._catalog.update_file_prescan_meta(
                file_id=meta.file_id,
                bucket_index_path=meta.bucket_index_path,
                line_count=meta.line_count,
                raw_ts_min=meta.raw_ts_min,
                raw_ts_max=meta.raw_ts_max,
                valid_ts_min=meta.valid_ts_min,
                valid_ts_max=meta.valid_ts_max,
                unsynced_line_ranges=new_ranges,
            )

    def _write_offsets_to_catalog(self, files: list, summary: BundleAlignmentSummary) -> None:
        for meta in files:
            if meta.offset_method in (
                AlignmentMethod.FILENAME_ANCHOR,
                AlignmentMethod.CLOCK_SYNC,
                AlignmentMethod.SEGMENTED,
            ):
                # per-file offset already set by decode stage; do not overwrite
                # with the controller-wide direct/two-hop result.
                continue
            offset = summary.sources.get(meta.controller)
            if offset is None:
                continue
            self._catalog.update_file_clock_offset(
                file_id=meta.file_id,
                clock_offset=offset.offset,
                offset_confidence=offset.confidence,
                offset_method=offset.method.value,
            )

    def _write_summary_to_bundle(
        self, bundle_id: UUID, summary: BundleAlignmentSummary
    ) -> None:
        payload = {
            "status": summary.status.value,
            "base_clock": summary.base_clock.value,
            "computed_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "sources": {
                c.value: {
                    "offset": o.offset,
                    "confidence": round(o.confidence, 4),
                    "method": o.method.value,
                    "sample_count": o.sample_count,
                }
                for c, o in summary.sources.items()
            },
            "warnings": list(summary.warnings),
        }
        self._catalog.set_bundle_alignment_summary(bundle_id, json.dumps(payload, ensure_ascii=False))
