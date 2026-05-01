from __future__ import annotations

import hashlib
import logging
import os
import shutil
import tarfile
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

_CHUNK = 1 << 20  # 1 MiB streaming chunk
_NESTED_ZIP_MAX_DEPTH = 5
_SKIP_NAMES = {".DS_Store"}
_SKIP_PREFIXES = ("__MACOSX/",)
_NESTED_ARCHIVE_SUFFIXES = (".zip", ".tar.gz", ".tgz", ".tar")


@dataclass(frozen=True)
class ExtractedFile:
    relative_path: str
    """POSIX-style path relative to the bundle root (post name-fix, post nested-zip flatten)."""
    temp_path: Path
    """Absolute path to the extracted file in a temp work dir; caller is responsible for moving it."""
    size: int
    sha256: str
    """SHA-256 of the file's bytes — used by the pipeline to drop duplicates that
    appear both as a top-level entry AND inside a nested archive that someone
    pre-expanded into the same bundle."""
    nested_depth: int = 0
    source_archive: Optional[str] = None
    """If extracted from a nested archive, the relative path of that archive within the bundle."""


def _fix_zip_name(raw: str, flag_bits: int) -> str:
    """Zip member names are UTF-8 only when bit 11 is set; otherwise default cp437.
    Many Chinese zips actually use GBK without setting the flag — re-decode."""
    if flag_bits & 0x800:
        return raw
    try:
        return raw.encode("cp437").decode("gbk")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return raw


def _should_skip(name: str) -> bool:
    if not name or name.endswith("/"):
        return True
    if any(name.startswith(p) for p in _SKIP_PREFIXES):
        return True
    base = name.rsplit("/", 1)[-1]
    if base in _SKIP_NAMES:
        return True
    return False


def _atomic_stream_copy(src, dst: Path) -> tuple[int, str]:
    """Copy a stream to dst via .partial + rename; return ``(bytes_written, sha256_hex)``."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    partial = dst.with_suffix(dst.suffix + ".partial")
    total = 0
    h = hashlib.sha256()
    with open(partial, "wb") as out:
        while True:
            chunk = src.read(_CHUNK)
            if not chunk:
                break
            out.write(chunk)
            h.update(chunk)
            total += len(chunk)
    os.replace(partial, dst)
    return total, h.hexdigest()


def _is_nested_archive(name: str) -> bool:
    lower = name.lower()
    return lower.endswith(_NESTED_ARCHIVE_SUFFIXES)


class Extractor:
    """Streaming archive extractor.

    Output strategy:
      - Each member is written into ``work_dir`` under a fresh uuid-named subdirectory,
        preserving the (name-fixed) relative path.
      - Caller (filestore) is responsible for the final controller-aware placement.
      - Nested ``.zip`` archives are recursively flattened: their inner paths are
        joined onto the outer archive member name (treated like a directory).
    """

    def __init__(self, work_root: Path):
        self._work_root = Path(work_root)
        self._work_root.mkdir(parents=True, exist_ok=True)

    def extract(self, archive_path: Path) -> Iterator[ExtractedFile]:
        archive_path = Path(archive_path)
        if not archive_path.is_file():
            raise FileNotFoundError(archive_path)
        work_dir = self._work_root / f"extract_{uuid.uuid4().hex}"
        work_dir.mkdir(parents=True, exist_ok=True)
        try:
            yield from self._extract_into(archive_path, work_dir, depth=0, source_archive=None)
        except Exception:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise

    def _extract_into(
        self,
        archive_path: Path,
        work_dir: Path,
        depth: int,
        source_archive: Optional[str],
    ) -> Iterator[ExtractedFile]:
        suffix = archive_path.suffix.lower()
        name = archive_path.name.lower()
        if suffix == ".zip":
            yield from self._extract_zip(archive_path, work_dir, depth, source_archive)
        elif name.endswith((".tar.gz", ".tgz", ".tar")) or suffix in {".gz"}:
            yield from self._extract_tar(archive_path, work_dir, depth, source_archive)
        else:
            raise ValueError(f"unsupported archive format: {archive_path}")

    def _extract_zip(
        self,
        archive_path: Path,
        work_dir: Path,
        depth: int,
        source_archive: Optional[str],
    ) -> Iterator[ExtractedFile]:
        with zipfile.ZipFile(archive_path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                fixed_name = _fix_zip_name(info.filename, info.flag_bits)
                if _should_skip(fixed_name):
                    continue
                target = work_dir / fixed_name
                with zf.open(info, "r") as src:
                    written, digest = _atomic_stream_copy(src, target)

                if _is_nested_archive(fixed_name) and depth < _NESTED_ZIP_MAX_DEPTH:
                    nested_dir = work_dir / (fixed_name + ".__expanded__")
                    nested_dir.mkdir(parents=True, exist_ok=True)
                    for inner in self._extract_into(
                        target, nested_dir, depth + 1, source_archive=fixed_name
                    ):
                        yield ExtractedFile(
                            relative_path=f"{fixed_name}/{inner.relative_path}",
                            temp_path=inner.temp_path,
                            size=inner.size,
                            sha256=inner.sha256,
                            nested_depth=inner.nested_depth,
                            source_archive=fixed_name,
                        )
                else:
                    yield ExtractedFile(
                        relative_path=fixed_name,
                        temp_path=target,
                        size=written,
                        sha256=digest,
                        nested_depth=depth,
                        source_archive=source_archive,
                    )

    def _extract_tar(
        self,
        archive_path: Path,
        work_dir: Path,
        depth: int,
        source_archive: Optional[str],
    ) -> Iterator[ExtractedFile]:
        with tarfile.open(archive_path, mode="r:*") as tf:
            for member in tf:
                if not member.isfile():
                    continue
                name = member.name
                if _should_skip(name):
                    continue
                src = tf.extractfile(member)
                if src is None:
                    continue
                target = work_dir / name
                with src:
                    written, digest = _atomic_stream_copy(src, target)
                if _is_nested_archive(name) and depth < _NESTED_ZIP_MAX_DEPTH:
                    nested_dir = work_dir / (name + ".__expanded__")
                    nested_dir.mkdir(parents=True, exist_ok=True)
                    for inner in self._extract_into(
                        target, nested_dir, depth + 1, source_archive=name
                    ):
                        yield ExtractedFile(
                            relative_path=f"{name}/{inner.relative_path}",
                            temp_path=inner.temp_path,
                            size=inner.size,
                            sha256=inner.sha256,
                            nested_depth=inner.nested_depth,
                            source_archive=name,
                        )
                else:
                    yield ExtractedFile(
                        relative_path=name,
                        temp_path=target,
                        size=written,
                        sha256=digest,
                        nested_depth=depth,
                        source_archive=source_archive,
                    )

    def cleanup(self, work_dir: Path) -> None:
        shutil.rmtree(work_dir, ignore_errors=True)


def make_temp_workspace() -> Path:
    return Path(tempfile.mkdtemp(prefix="log_pipeline_"))
