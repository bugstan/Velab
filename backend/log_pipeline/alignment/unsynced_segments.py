from __future__ import annotations

from typing import Optional


def refine_with_clock_sync(
    existing_ranges: list[tuple[int, int]],
    clock_sync_line_no: Optional[int],
) -> list[tuple[int, int]]:
    """Tighten unsynced ranges given the line where ``tbox_clock_sync`` fired.

    Per CLAUDE.md §6.5.4: when a clock-sync anchor exists at line K, the
    pre-sync segment is exactly ``(0, K-1)``; everything past K is synced.
    Without a sync anchor we keep the prescan-derived ranges (typically based on
    timestamps below MIN_VALID_TS).
    """
    if clock_sync_line_no is None or clock_sync_line_no <= 0:
        return list(existing_ranges)
    return [(0, clock_sync_line_no - 1)]


def merge_overlapping_ranges(
    ranges: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Sort + merge contiguous/overlapping (start, end) line ranges (inclusive)."""
    if not ranges:
        return []
    s = sorted(ranges)
    merged: list[tuple[int, int]] = [s[0]]
    for start, end in s[1:]:
        cur_s, cur_e = merged[-1]
        if start <= cur_e + 1:
            merged[-1] = (cur_s, max(cur_e, end))
        else:
            merged.append((start, end))
    return merged
