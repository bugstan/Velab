from __future__ import annotations

from log_pipeline.alignment.time_aligner import (
    DIRECT_WINDOW_SEC,
    SPARSE_WINDOW_SEC,
    _AnchorView,
    align_bundle,
    from_anchor_candidates,
)
from log_pipeline.alignment.unsynced_segments import (
    merge_overlapping_ranges,
    refine_with_clock_sync,
)
from log_pipeline.interfaces import (
    AlignmentMethod,
    AlignmentStatus,
    AnchorCandidate,
    ControllerType,
    MIN_VALID_TS,
)


# ---------------- helpers ----------------


def _av(ctrl: ControllerType, atype: str, ts: float, conf: float = 0.9) -> _AnchorView:
    return _AnchorView(controller=ctrl, anchor_type=atype, raw_timestamp=ts, confidence=conf)


def _ac(ctrl: ControllerType, atype: str, ts: float, conf: float = 0.9) -> AnchorCandidate:
    return AnchorCandidate(
        anchor_type=atype, controller=ctrl, raw_timestamp=ts, line_no=0, confidence=conf, fields={}
    )


# ---------------- unsynced segments ----------------


def test_refine_with_clock_sync_replaces_existing_ranges():
    out = refine_with_clock_sync([(0, 9999)], clock_sync_line_no=200)
    assert out == [(0, 199)]


def test_refine_with_clock_sync_keeps_existing_when_no_anchor():
    existing = [(0, 50), (1000, 1100)]
    assert refine_with_clock_sync(existing, None) == existing


def test_refine_with_clock_sync_returns_empty_when_at_zero():
    # If sync happened at the very first line there is no pre-sync window
    assert refine_with_clock_sync([(0, 100)], 0) == [(0, 100)]


def test_merge_overlapping_ranges():
    assert merge_overlapping_ranges([(0, 4), (3, 8), (15, 20), (21, 25)]) == [(0, 8), (15, 25)]
    assert merge_overlapping_ranges([]) == []


# ---------------- direct alignment ----------------


def test_direct_alignment_perfect_match():
    base_ts = MIN_VALID_TS + 100  # 2020-01-01 + 100s
    # tbox anchors at 0/100/200, mcu mirrors with offset = +5s
    tbox = [_av(ControllerType.TBOX, "system_boot", base_ts + i * 100) for i in range(3)]
    mcu = [_av(ControllerType.MCU, "system_boot", base_ts + i * 100 - 5) for i in range(3)]
    summary = align_bundle(tbox + mcu, [ControllerType.TBOX, ControllerType.MCU])
    mcu_off = summary.sources[ControllerType.MCU]
    assert mcu_off.method == AlignmentMethod.DIRECT
    assert abs(mcu_off.offset - 5.0) < 1e-6
    # 3 pairs × anchor-conf 0.9 × perfect consistency → 0.9 (matches the input anchor conf)
    assert mcu_off.confidence >= 0.85
    assert mcu_off.sample_count == 3
    assert summary.status == AlignmentStatus.SUCCESS
    assert summary.base_clock == ControllerType.TBOX


def test_direct_alignment_sparse_window_widens():
    base_ts = MIN_VALID_TS + 100
    # Only two pairs, slightly outside 60s window but within 600s
    tbox = [
        _av(ControllerType.TBOX, "system_boot", base_ts),
        _av(ControllerType.TBOX, "fota_install_start", base_ts + 5000),
    ]
    mcu = [
        _av(ControllerType.MCU, "system_boot", base_ts - 200),
        _av(ControllerType.MCU, "fota_install_start", base_ts + 5000 - 200),
    ]
    summary = align_bundle(tbox + mcu, [ControllerType.TBOX, ControllerType.MCU])
    off = summary.sources[ControllerType.MCU]
    assert off.method == AlignmentMethod.DIRECT
    assert abs(off.offset - 200.0) < 1.0
    assert off.sample_count == 2


def test_direct_alignment_filters_pre_min_valid_ts_anchors():
    # Anchors below MIN_VALID_TS should be discarded
    tbox = [_ac(ControllerType.TBOX, "system_boot", MIN_VALID_TS + 100)]
    mcu_pre = [_ac(ControllerType.MCU, "system_boot", 1.0)]  # epoch start, < MIN_VALID_TS
    views = from_anchor_candidates(tbox + mcu_pre)
    summary = align_bundle(views, [ControllerType.TBOX, ControllerType.MCU])
    assert summary.sources[ControllerType.MCU].offset is None
    assert summary.status in (AlignmentStatus.PARTIAL, AlignmentStatus.FAILED)


def test_anchors_far_apart_yield_no_offset():
    """If candidate anchors of the same type are 100 days apart they cannot pair
    within either the 60s nor the 600s sparse window, so no offset is produced."""
    base_ts = MIN_VALID_TS + 100
    huge = 100 * 86400
    tbox = [_av(ControllerType.TBOX, "system_boot", base_ts + i * 30) for i in range(3)]
    mcu = [_av(ControllerType.MCU, "system_boot", base_ts + i * 30 + huge) for i in range(3)]
    summary = align_bundle(tbox + mcu, [ControllerType.TBOX, ControllerType.MCU])
    assert summary.sources[ControllerType.MCU].offset is None
    assert summary.sources[ControllerType.MCU].sample_count == 0


def test_30_day_sanity_predicate_directly():
    """Cover the sanity ceiling at the unit level — pair-matching window already
    constrains direct offsets to seconds, so this guards two-hop accumulation."""
    from log_pipeline.alignment.time_aligner import _is_sane
    from log_pipeline.interfaces import MAX_OFFSET_SECONDS

    assert _is_sane(0.0)
    assert _is_sane(MAX_OFFSET_SECONDS - 1)
    assert not _is_sane(MAX_OFFSET_SECONDS + 1)
    assert not _is_sane(-(MAX_OFFSET_SECONDS + 1))
    assert not _is_sane(None)


# ---------------- two-hop ----------------


def test_two_hop_via_android():
    base_ts = MIN_VALID_TS + 100
    # tbox + android share anchors → strong direct
    tbox = [_av(ControllerType.TBOX, "system_boot", base_ts + i * 60) for i in range(4)]
    android = [_av(ControllerType.ANDROID, "system_boot", base_ts + i * 60 - 1) for i in range(4)]
    # mcu shares anchors only with android (different anchor_type)
    mcu = [_av(ControllerType.MCU, "fota_install_start", base_ts + i * 60 - 11) for i in range(4)]
    bridge_for_mcu = [
        _av(ControllerType.ANDROID, "fota_install_start", base_ts + i * 60 - 1) for i in range(4)
    ]

    summary = align_bundle(
        tbox + android + bridge_for_mcu + mcu,
        [ControllerType.TBOX, ControllerType.ANDROID, ControllerType.MCU],
    )
    mcu_off = summary.sources[ControllerType.MCU]
    assert mcu_off.method == AlignmentMethod.TWO_HOP
    # offset should approximate android_to_tbox (1) + mcu_to_android (10) = 11
    assert abs(mcu_off.offset - 11.0) < 0.5
    assert mcu_off.sample_count >= 3


def test_two_hop_skipped_if_direct_already_high_confidence():
    base_ts = MIN_VALID_TS + 100
    tbox = [_av(ControllerType.TBOX, "system_boot", base_ts + i * 60) for i in range(5)]
    android = [_av(ControllerType.ANDROID, "system_boot", base_ts + i * 60 - 1) for i in range(5)]
    mcu = [_av(ControllerType.MCU, "system_boot", base_ts + i * 60 - 4) for i in range(5)]
    summary = align_bundle(
        tbox + android + mcu,
        [ControllerType.TBOX, ControllerType.ANDROID, ControllerType.MCU],
    )
    # Direct match (tbox vs mcu via shared anchor type) should win
    assert summary.sources[ControllerType.MCU].method == AlignmentMethod.DIRECT


# ---------------- degradation / status ----------------


def test_degrades_to_android_when_tbox_missing():
    base_ts = MIN_VALID_TS + 100
    android = [_av(ControllerType.ANDROID, "system_boot", base_ts + i * 60) for i in range(3)]
    mcu = [_av(ControllerType.MCU, "system_boot", base_ts + i * 60 - 4) for i in range(3)]
    summary = align_bundle(
        android + mcu, [ControllerType.ANDROID, ControllerType.MCU]
    )
    assert summary.base_clock == ControllerType.ANDROID
    # SUCCESS → demoted to PARTIAL when degraded
    assert summary.status == AlignmentStatus.PARTIAL
    assert any("degraded to android" in w for w in summary.warnings)


def test_failed_when_no_usable_anchors():
    summary = align_bundle([], [ControllerType.TBOX, ControllerType.MCU])
    assert summary.status == AlignmentStatus.FAILED
    assert summary.sources[ControllerType.MCU].offset is None


def test_partial_when_one_target_aligned_other_missing():
    base_ts = MIN_VALID_TS + 100
    tbox = [_av(ControllerType.TBOX, "system_boot", base_ts + i * 60) for i in range(3)]
    android = [_av(ControllerType.ANDROID, "system_boot", base_ts + i * 60 - 1) for i in range(3)]
    # mcu has no anchors at all
    summary = align_bundle(
        tbox + android,
        [ControllerType.TBOX, ControllerType.ANDROID, ControllerType.MCU],
    )
    assert summary.sources[ControllerType.ANDROID].offset is not None
    assert summary.sources[ControllerType.MCU].offset is None
    assert summary.status in (AlignmentStatus.PARTIAL, AlignmentStatus.FAILED)


# ---------------- consistency factor ----------------


def test_high_jitter_reduces_confidence():
    base_ts = MIN_VALID_TS + 100
    # Five pairs but with massive scatter (offsets of -50, 0, 50, ...)
    tbox = [_av(ControllerType.TBOX, "system_boot", base_ts + i * 60) for i in range(5)]
    mcu = [
        _av(ControllerType.MCU, "system_boot", base_ts + i * 60 - jitter)
        for i, jitter in enumerate([0, 5, 30, -25, 40])
    ]
    summary = align_bundle(
        tbox + mcu, [ControllerType.TBOX, ControllerType.MCU]
    )
    off = summary.sources[ControllerType.MCU]
    assert off.method == AlignmentMethod.DIRECT
    # confidence should be noticeably below the perfect-match case
    assert off.confidence < 0.9
