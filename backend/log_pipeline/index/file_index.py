from __future__ import annotations

import struct
from pathlib import Path
from typing import Iterator

from log_pipeline.interfaces import BUCKET_SECONDS

_RECORD = struct.Struct("<qqq")  # bucket_id, byte_offset, line_no
RECORD_SIZE = _RECORD.size


class BucketIndexWriter:
    """5-minute bucket index writer.

    Writes one record per *bucket transition*: when a line's bucket id differs from
    the previous recorded one, append (bucket_id, byte_offset, line_no). Records are
    therefore strictly increasing in bucket_id and represent the first line that
    landed in each bucket.
    """

    def __init__(self, path: Path):
        self._path = Path(path)
        self._partial = self._path.with_suffix(self._path.suffix + ".partial")
        self._partial.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(self._partial, "wb")
        self._last_bucket: int = -1
        self._records_written = 0

    def append(self, raw_ts: float, byte_offset: int, line_no: int) -> None:
        bucket = int(raw_ts // BUCKET_SECONDS)
        if bucket == self._last_bucket:
            return
        self._f.write(_RECORD.pack(bucket, byte_offset, line_no))
        self._last_bucket = bucket
        self._records_written += 1

    @property
    def records_written(self) -> int:
        return self._records_written

    def close(self) -> Path:
        self._f.close()
        self._partial.replace(self._path)
        return self._path

    def abort(self) -> None:
        try:
            self._f.close()
        finally:
            try:
                self._partial.unlink(missing_ok=True)
            except OSError:
                pass

    def __enter__(self) -> "BucketIndexWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.abort()
        else:
            self.close()


def read_bucket_index(path: Path) -> Iterator[tuple[int, int, int]]:
    """Iterate ``(bucket_id, byte_offset, line_no)`` records from a .idx file."""
    with open(path, "rb") as f:
        while True:
            chunk = f.read(RECORD_SIZE)
            if len(chunk) < RECORD_SIZE:
                return
            yield _RECORD.unpack(chunk)
