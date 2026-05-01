from __future__ import annotations

import logging
import os
import re
import shutil
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import UUID

from log_pipeline.interfaces import ControllerType, LogFileMeta

logger = logging.getLogger(__name__)

_UNSAFE_CHARS = re.compile(r"[\x00-\x1f/\\]")
_MAX_BASENAME_LEN = 200


def _sanitize_basename(name: str) -> str:
    base = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    base = _UNSAFE_CHARS.sub("_", base)
    if len(base) > _MAX_BASENAME_LEN:
        stem, dot, ext = base.rpartition(".")
        keep = _MAX_BASENAME_LEN - len(ext) - 1 if dot else _MAX_BASENAME_LEN
        base = (stem[:keep] + "." + ext) if dot else base[:_MAX_BASENAME_LEN]
    return base or "unnamed"


class FileStore:
    """Owns the on-disk layout for raw uploaded files and per-bundle audit logs.

    Layout:
        {store_root}/
          {bundle_id}/
            _processing.log
            {controller}/
              {file_id}__{sanitized_basename}
              ...
    """

    def __init__(self, store_root: Path):
        self._root = Path(store_root)
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def bundle_dir(self, bundle_id: UUID) -> Path:
        return self._root / str(bundle_id)

    def init_bundle(self, bundle_id: UUID) -> Path:
        d = self.bundle_dir(bundle_id)
        d.mkdir(parents=True, exist_ok=True)
        log_path = d / "_processing.log"
        if not log_path.exists():
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(f"# bundle {bundle_id}\n")
                f.write(f"# created_at {self._iso_now()}\n")
        return d

    def store_file(
        self,
        bundle_id: UUID,
        controller: ControllerType,
        bundle_relative_path: str,
        source_path: Path,
        sha256: str | None = None,
    ) -> LogFileMeta:
        """Move ``source_path`` into the canonical bundle layout.

        ``bundle_relative_path`` is the full POSIX path inside the archive (used for traceability;
        on-disk filename uses only its basename).
        """
        file_id = uuid.uuid4()
        original_name = bundle_relative_path.rsplit("/", 1)[-1]
        safe_name = _sanitize_basename(original_name)
        target_dir = self.bundle_dir(bundle_id) / controller.value
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{file_id}__{safe_name}"

        if target.exists():
            target = target_dir / f"{file_id}_{uuid.uuid4().hex[:8]}__{safe_name}"

        try:
            os.replace(source_path, target)
        except OSError:
            shutil.copy2(source_path, target)
            try:
                os.remove(source_path)
            except OSError:
                pass

        size = target.stat().st_size
        return LogFileMeta(
            file_id=file_id,
            bundle_id=bundle_id,
            controller=controller,
            original_name=original_name,
            stored_path=str(target),
            bundle_relative_path=bundle_relative_path,
            size_bytes=size,
            sha256=sha256,
        )

    def append_processing_log(self, bundle_id: UUID, message: str) -> None:
        path = self.bundle_dir(bundle_id) / "_processing.log"
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{self._iso_now()}] {message}\n")

    @contextmanager
    def processing_log(self, bundle_id: UUID, stage: str) -> Iterator[None]:
        self.append_processing_log(bundle_id, f"stage={stage} status=start")
        try:
            yield
        except Exception as e:
            self.append_processing_log(bundle_id, f"stage={stage} status=error error={e!r}")
            raise
        else:
            self.append_processing_log(bundle_id, f"stage={stage} status=ok")

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
