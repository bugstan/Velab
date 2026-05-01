from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Optional
from uuid import UUID

from log_pipeline.interfaces import (
    RAW_LINE_TRUNCATE_BYTES,
    AnchorCandidate,
    ControllerType,
    ImportantEvent,
)

_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS events (
      event_id              TEXT PRIMARY KEY,
      bundle_id             TEXT NOT NULL,
      file_id               TEXT NOT NULL,
      controller            TEXT NOT NULL,
      event_type            TEXT NOT NULL,
      raw_timestamp         REAL,
      aligned_timestamp     REAL,
      alignment_quality     REAL NOT NULL DEFAULT 0,
      line_no               INTEGER NOT NULL,
      byte_offset           INTEGER,
      raw_line              TEXT NOT NULL,
      extracted_fields_json TEXT NOT NULL DEFAULT '{}',
      created_at            TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_events_bundle_type ON events(bundle_id, event_type);",
    "CREATE INDEX IF NOT EXISTS idx_events_bundle_time ON events(bundle_id, raw_timestamp);",
    """
    CREATE TABLE IF NOT EXISTS anchors (
      anchor_id     TEXT PRIMARY KEY,
      bundle_id     TEXT NOT NULL,
      file_id       TEXT NOT NULL,
      controller    TEXT NOT NULL,
      anchor_type   TEXT NOT NULL,
      raw_timestamp REAL,
      line_no       INTEGER NOT NULL,
      byte_offset   INTEGER,
      confidence    REAL NOT NULL,
      fields_json   TEXT NOT NULL DEFAULT '{}',
      created_at    TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_anchors_bundle_type ON anchors(bundle_id, anchor_type);",
    "CREATE INDEX IF NOT EXISTS idx_anchors_bundle_file ON anchors(bundle_id, file_id);",
]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _truncate_raw_line(line: str) -> str:
    encoded = line.encode("utf-8", errors="replace")
    if len(encoded) <= RAW_LINE_TRUNCATE_BYTES:
        return line
    return encoded[:RAW_LINE_TRUNCATE_BYTES].decode("utf-8", errors="replace")


class EventDB:
    """Persistence for important events and anchor candidates.

    Separate class from ``Catalog`` even though they share the same SQLite file —
    keeps their schema concerns independent and lets either be re-run without
    perturbing the other (re-prescan with new rules: TRUNCATE events / anchors,
    rerun; catalog stays intact).
    """

    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._tls = threading.local()
        self._ensure_schema()

    def _conn(self) -> sqlite3.Connection:
        c = getattr(self._tls, "conn", None)
        if c is None:
            c = sqlite3.connect(self._db_path, isolation_level=None)
            c.execute("PRAGMA journal_mode=WAL;")
            c.execute("PRAGMA foreign_keys=OFF;")
            c.row_factory = sqlite3.Row
            self._tls.conn = c
        return c

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        conn = self._conn()
        conn.execute("BEGIN")
        try:
            yield conn
        except Exception:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")

    def _ensure_schema(self) -> None:
        conn = self._conn()
        for stmt in _SCHEMA:
            conn.execute(stmt)

    # --- events ---

    def insert_events_batch(self, events: Iterable[ImportantEvent]) -> int:
        rows = []
        now = _iso_now()
        count = 0
        for ev in events:
            rows.append(
                (
                    str(ev.event_id),
                    str(ev.bundle_id),
                    str(ev.file_id),
                    ev.controller.value,
                    ev.event_type,
                    ev.raw_timestamp,
                    ev.aligned_timestamp,
                    ev.alignment_quality,
                    ev.line_no,
                    None,
                    _truncate_raw_line(ev.raw_line),
                    json.dumps(ev.extracted_fields, ensure_ascii=False),
                    now,
                )
            )
            count += 1
        if not rows:
            return 0
        with self._tx() as conn:
            conn.executemany(
                "INSERT INTO events (event_id, bundle_id, file_id, controller, event_type, "
                "raw_timestamp, aligned_timestamp, alignment_quality, line_no, byte_offset, "
                "raw_line, extracted_fields_json, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )
        return count

    def list_events(
        self,
        bundle_id: UUID,
        event_types: Optional[list[str]] = None,
        controllers: Optional[list[ControllerType]] = None,
        start: Optional[float] = None,
        end: Optional[float] = None,
    ) -> list[dict]:
        conds = ["bundle_id = ?"]
        args: list = [str(bundle_id)]
        if event_types:
            conds.append("event_type IN (" + ",".join("?" * len(event_types)) + ")")
            args.extend(event_types)
        if controllers:
            conds.append("controller IN (" + ",".join("?" * len(controllers)) + ")")
            args.extend(c.value for c in controllers)
        if start is not None:
            conds.append("(raw_timestamp IS NULL OR raw_timestamp >= ?)")
            args.append(start)
        if end is not None:
            conds.append("(raw_timestamp IS NULL OR raw_timestamp <= ?)")
            args.append(end)
        sql = (
            "SELECT * FROM events WHERE "
            + " AND ".join(conds)
            + " ORDER BY raw_timestamp NULLS LAST, line_no"
        )
        return [dict(r) for r in self._conn().execute(sql, args).fetchall()]

    def count_events_by_type(self, bundle_id: UUID) -> dict[str, int]:
        rows = self._conn().execute(
            "SELECT event_type, COUNT(*) AS n FROM events WHERE bundle_id=? GROUP BY event_type",
            (str(bundle_id),),
        ).fetchall()
        return {r["event_type"]: r["n"] for r in rows}

    # --- anchors ---

    def insert_anchors_batch(
        self,
        bundle_id: UUID,
        file_id: UUID,
        anchors: Iterable[AnchorCandidate],
    ) -> int:
        rows = []
        now = _iso_now()
        count = 0
        for a in anchors:
            rows.append(
                (
                    str(uuid.uuid4()),
                    str(bundle_id),
                    str(file_id),
                    a.controller.value,
                    a.anchor_type,
                    a.raw_timestamp,
                    a.line_no,
                    None,
                    a.confidence,
                    json.dumps(a.fields, ensure_ascii=False),
                    now,
                )
            )
            count += 1
        if not rows:
            return 0
        with self._tx() as conn:
            conn.executemany(
                "INSERT INTO anchors (anchor_id, bundle_id, file_id, controller, anchor_type, "
                "raw_timestamp, line_no, byte_offset, confidence, fields_json, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )
        return count

    def list_anchors(self, bundle_id: UUID) -> list[dict]:
        rows = self._conn().execute(
            "SELECT * FROM anchors WHERE bundle_id=? ORDER BY raw_timestamp, line_no",
            (str(bundle_id),),
        ).fetchall()
        return [dict(r) for r in rows]

    def count_events_by_type_global(self) -> dict[str, int]:
        rows = self._conn().execute(
            "SELECT event_type, COUNT(*) AS n FROM events GROUP BY event_type"
        ).fetchall()
        return {r["event_type"]: r["n"] for r in rows}

    def count_anchors_by_type(self, bundle_id: UUID) -> dict[str, int]:
        rows = self._conn().execute(
            "SELECT anchor_type, COUNT(*) AS n FROM anchors WHERE bundle_id=? GROUP BY anchor_type",
            (str(bundle_id),),
        ).fetchall()
        return {r["anchor_type"]: r["n"] for r in rows}

    def clear_for_bundle(self, bundle_id: UUID) -> None:
        """Wipe events/anchors for a bundle. Used when re-running prescan."""
        with self._tx() as conn:
            conn.execute("DELETE FROM events WHERE bundle_id=?", (str(bundle_id),))
            conn.execute("DELETE FROM anchors WHERE bundle_id=?", (str(bundle_id),))

    def clear_event_type(self, bundle_id: UUID, event_type: str) -> None:
        """Wipe events of one type for a bundle. Used by post-processors that
        regenerate their own events idempotently (e.g. crash heuristic)."""
        with self._tx() as conn:
            conn.execute(
                "DELETE FROM events WHERE bundle_id=? AND event_type=?",
                (str(bundle_id), event_type),
            )
