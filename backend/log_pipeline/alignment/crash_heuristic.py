from __future__ import annotations

import logging
import uuid
from typing import Optional
from uuid import UUID

from log_pipeline.interfaces import ControllerType, ImportantEvent
from log_pipeline.storage.catalog import Catalog
from log_pipeline.storage.eventdb import EventDB

logger = logging.getLogger(__name__)


_SHORT_CAPTURE_SEC = 90.0
"""Below this captured-runtime, we treat the boot session as suspicious."""

_QUICK_REBOOT_GAP_SEC = 300.0
"""Gap (boot wall-clock to next boot wall-clock) below which we call it a quick reboot."""


def detect_suspected_crashes(
    bundle_id: UUID,
    catalog: Catalog,
    eventdb: EventDB,
) -> int:
    """Cross-file pass: pair adjacent ``boot_session`` events and flag short
    captures whose successor boot follows quickly. Emits one
    ``system_crash_suspected`` event per match. Idempotent — clears prior
    suspected-crash events for the bundle before re-emitting.

    Returns the number of suspected crashes emitted.
    """
    eventdb.clear_event_type(bundle_id, "system_crash_suspected")

    boot_events = [
        e for e in eventdb.list_events(bundle_id, event_types=["boot_session"])
        if e.get("aligned_timestamp") is not None
    ]
    if len(boot_events) < 2:
        return 0
    boot_events.sort(key=lambda e: e["aligned_timestamp"])

    # Capture-runtime per file is ``raw_ts_max - raw_ts_min`` (seconds since boot).
    files_by_id = {str(m.file_id): m for m in catalog.list_files_by_bundle(bundle_id)}

    emitted: list[ImportantEvent] = []
    for cur, nxt in zip(boot_events, boot_events[1:]):
        meta = files_by_id.get(cur["file_id"])
        if meta is None or meta.raw_ts_max is None:
            continue
        capture_sec = float(meta.raw_ts_max)
        gap_sec = float(nxt["aligned_timestamp"]) - float(cur["aligned_timestamp"])
        if capture_sec >= _SHORT_CAPTURE_SEC or gap_sec >= _QUICK_REBOOT_GAP_SEC:
            continue
        emitted.append(_make_event(meta.bundle_id, meta.file_id, meta.controller, cur, capture_sec, gap_sec))

    if emitted:
        eventdb.insert_events_batch(emitted)
    return len(emitted)


def _make_event(
    bundle_id: UUID,
    file_id: UUID,
    controller: ControllerType,
    cur_boot_event: dict,
    capture_sec: float,
    gap_sec: float,
) -> ImportantEvent:
    boot_epoch = float(cur_boot_event["aligned_timestamp"])
    return ImportantEvent(
        event_id=uuid.uuid4(),
        bundle_id=bundle_id,
        file_id=file_id,
        controller=controller,
        event_type="system_crash_suspected",
        raw_timestamp=0.0,
        aligned_timestamp=boot_epoch,
        alignment_quality=0.99,
        line_no=0,
        raw_line=cur_boot_event.get("raw_line", ""),
        extracted_fields={
            "capture_duration_sec": round(capture_sec, 3),
            "gap_to_next_boot_sec": round(gap_sec, 3),
            "heuristic": (
                f"capture<{_SHORT_CAPTURE_SEC:.0f}s and next_boot<{_QUICK_REBOOT_GAP_SEC:.0f}s"
            ),
        },
    )
