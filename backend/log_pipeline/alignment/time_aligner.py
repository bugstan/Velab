from __future__ import annotations

import bisect
import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Optional

from log_pipeline.interfaces import (
    MAX_OFFSET_SECONDS,
    MIN_VALID_TS,
    AlignmentMethod,
    AlignmentStatus,
    AnchorCandidate,
    BundleAlignmentSummary,
    ControllerType,
    SourceOffset,
)

logger = logging.getLogger(__name__)

DIRECT_WINDOW_SEC = 60.0
SPARSE_THRESHOLD_PAIRS = 3
SPARSE_WINDOW_SEC = 600.0
TWO_HOP_PENALTY = 0.95
TWO_HOP_BRIDGE = ControllerType.ANDROID
SUCCESS_CONFIDENCE_FLOOR = 0.8
PARTIAL_RATIO_FLOOR = 0.5

CONSISTENCY_STDEV_THRESHOLD = 5.0
CONSISTENCY_MIN_FACTOR = 0.6


@dataclass(frozen=True)
class _AnchorView:
    """Lightweight view used internally by the aligner.

    Strips DB row noise — what we need is (controller, anchor_type, raw_ts, confidence).
    """

    controller: ControllerType
    anchor_type: str
    raw_timestamp: float
    confidence: float


def to_anchor_view(rows: Iterable[dict]) -> list[_AnchorView]:
    """Convert anchor table rows (from EventDB.list_anchors) to internal views,
    discarding pre-MIN_VALID_TS anchors (they belong to unsynced segments)."""
    out: list[_AnchorView] = []
    for r in rows:
        ts = r.get("raw_timestamp") if isinstance(r, dict) else None
        if ts is None or ts < MIN_VALID_TS:
            continue
        try:
            ctrl = ControllerType(r["controller"])
        except ValueError:
            continue
        out.append(
            _AnchorView(
                controller=ctrl,
                anchor_type=r["anchor_type"],
                raw_timestamp=float(ts),
                confidence=float(r["confidence"]),
            )
        )
    return out


def from_anchor_candidates(
    candidates: Iterable[AnchorCandidate],
) -> list[_AnchorView]:
    """Adapter for synthetic test fixtures that produce ``AnchorCandidate`` objects."""
    out: list[_AnchorView] = []
    for a in candidates:
        if a.raw_timestamp < MIN_VALID_TS:
            continue
        out.append(
            _AnchorView(
                controller=a.controller,
                anchor_type=a.anchor_type,
                raw_timestamp=a.raw_timestamp,
                confidence=a.confidence,
            )
        )
    return out


def _group_by_type(anchors: Iterable[_AnchorView]) -> dict[str, list[_AnchorView]]:
    out: dict[str, list[_AnchorView]] = defaultdict(list)
    for a in anchors:
        out[a.anchor_type].append(a)
    for v in out.values():
        v.sort(key=lambda a: a.raw_timestamp)
    return out


def _match_pairs_for_type(
    base: list[_AnchorView],
    src: list[_AnchorView],
    window: float,
) -> list[tuple[_AnchorView, _AnchorView]]:
    """Greedy nearest-neighbour pairing within ``window`` seconds.

    Both lists are pre-sorted by raw_timestamp. We walk src; for each src anchor
    we binary-search the closest unmatched base anchor and pair if within window.
    """
    if not base or not src:
        return []
    base_ts = [a.raw_timestamp for a in base]
    used: set[int] = set()
    pairs: list[tuple[_AnchorView, _AnchorView]] = []
    for s in src:
        i = bisect.bisect_left(base_ts, s.raw_timestamp)
        candidates_idx: list[int] = []
        for j in (i - 1, i):
            if 0 <= j < len(base) and j not in used:
                candidates_idx.append(j)
        if not candidates_idx:
            continue
        # pick the closest in time
        best = min(candidates_idx, key=lambda j: abs(base_ts[j] - s.raw_timestamp))
        if abs(base_ts[best] - s.raw_timestamp) <= window:
            used.add(best)
            pairs.append((base[best], s))
    return pairs


def _match_all_pairs(
    base_by_type: dict[str, list[_AnchorView]],
    src_by_type: dict[str, list[_AnchorView]],
    window: float,
) -> list[tuple[_AnchorView, _AnchorView]]:
    out: list[tuple[_AnchorView, _AnchorView]] = []
    for atype, base_list in base_by_type.items():
        src_list = src_by_type.get(atype)
        if not src_list:
            continue
        out.extend(_match_pairs_for_type(base_list, src_list, window))
    return out


def _weighted_mean(values: list[float], weights: list[float]) -> float:
    total_w = sum(weights)
    if total_w <= 0:
        return sum(values) / len(values)
    return sum(v * w for v, w in zip(values, weights)) / total_w


def _weighted_stdev(values: list[float], weights: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _weighted_mean(values, weights)
    total_w = sum(weights) or len(values)
    var = sum(w * (v - mean) ** 2 for v, w in zip(values, weights)) / total_w
    return math.sqrt(max(var, 0.0))


def _consistency_factor(stdev: float) -> float:
    if stdev <= CONSISTENCY_STDEV_THRESHOLD:
        return 1.0
    # linearly decay to CONSISTENCY_MIN_FACTOR over the next 5x stdev range
    excess = stdev - CONSISTENCY_STDEV_THRESHOLD
    decay_range = CONSISTENCY_STDEV_THRESHOLD * 5
    factor = 1.0 - (1.0 - CONSISTENCY_MIN_FACTOR) * min(excess / decay_range, 1.0)
    return max(factor, CONSISTENCY_MIN_FACTOR)


def _compute_offset_from_pairs(
    pairs: list[tuple[_AnchorView, _AnchorView]],
) -> tuple[float, float]:
    """Return (offset, confidence) given (base, src) anchor pairs.

    offset = weighted_mean(base_ts - src_ts), weights = base.confidence × src.confidence
    confidence = min(n/2, 1.0) × avg_anchor_confidence × consistency_factor(stdev)
    """
    diffs = [b.raw_timestamp - s.raw_timestamp for b, s in pairs]
    weights = [max(b.confidence * s.confidence, 1e-6) for b, s in pairs]
    offset = _weighted_mean(diffs, weights)
    stdev = _weighted_stdev(diffs, weights)
    avg_anchor_conf = sum(weights) / len(weights)
    n = len(pairs)
    confidence = min(n / 2.0, 1.0) * math.sqrt(avg_anchor_conf) * _consistency_factor(stdev)
    return offset, max(0.0, min(confidence, 1.0))


def _direct_align(
    base_by_type: dict[str, list[_AnchorView]],
    src_by_type: dict[str, list[_AnchorView]],
) -> Optional[tuple[float, float, int]]:
    pairs = _match_all_pairs(base_by_type, src_by_type, DIRECT_WINDOW_SEC)
    if len(pairs) < SPARSE_THRESHOLD_PAIRS:
        widened = _match_all_pairs(base_by_type, src_by_type, SPARSE_WINDOW_SEC)
        if len(widened) > len(pairs):
            pairs = widened
    if not pairs:
        return None
    offset, conf = _compute_offset_from_pairs(pairs)
    return offset, conf, len(pairs)


def _two_hop_align(
    bridge_by_type: dict[str, list[_AnchorView]],
    src_by_type: dict[str, list[_AnchorView]],
    bridge_offset: float,
    bridge_confidence: float,
) -> Optional[tuple[float, float, int]]:
    pairs = _match_all_pairs(bridge_by_type, src_by_type, DIRECT_WINDOW_SEC)
    if len(pairs) < SPARSE_THRESHOLD_PAIRS:
        widened = _match_all_pairs(bridge_by_type, src_by_type, SPARSE_WINDOW_SEC)
        if len(widened) > len(pairs):
            pairs = widened
    if not pairs:
        return None
    diffs = [b.raw_timestamp - s.raw_timestamp for b, s in pairs]
    weights = [max(b.confidence * s.confidence, 1e-6) for b, s in pairs]
    bridge_to_src_offset = _weighted_mean(diffs, weights)
    stdev = _weighted_stdev(diffs, weights)
    avg_anchor_conf = sum(weights) / len(weights)
    n = len(pairs)
    confidence = (
        min(n / 2.0, 1.0)
        * math.sqrt(avg_anchor_conf)
        * _consistency_factor(stdev)
        * bridge_confidence
        * TWO_HOP_PENALTY
    )
    return bridge_offset + bridge_to_src_offset, max(0.0, min(confidence, 1.0)), n


_NULL_OFFSET = SourceOffset(
    offset=None, confidence=0.0, method=AlignmentMethod.NONE, sample_count=0
)


def _is_sane(offset: Optional[float]) -> bool:
    return offset is not None and abs(offset) <= MAX_OFFSET_SECONDS


def align_bundle(
    anchors: list[_AnchorView],
    target_controllers: Iterable[ControllerType],
) -> BundleAlignmentSummary:
    """Compute per-controller offsets relative to tbox (or android if tbox is empty).

    `anchors` should contain only anchors with raw_timestamp ≥ MIN_VALID_TS.
    `target_controllers` is the list of controllers present in the bundle.
    """
    by_ctrl: dict[ControllerType, dict[str, list[_AnchorView]]] = {
        c: defaultdict(list) for c in target_controllers
    }
    for a in anchors:
        by_ctrl.setdefault(a.controller, defaultdict(list))[a.anchor_type].append(a)
    for type_map in by_ctrl.values():
        for v in type_map.values():
            v.sort(key=lambda x: x.raw_timestamp)

    base = ControllerType.TBOX
    warnings: list[str] = []
    degraded_to_android = False

    if not by_ctrl.get(base):
        if by_ctrl.get(ControllerType.ANDROID):
            base = ControllerType.ANDROID
            degraded_to_android = True
            warnings.append("tbox has no usable anchors — degraded to android base clock")
        else:
            warnings.append("neither tbox nor android has usable anchors — alignment FAILED")
            return BundleAlignmentSummary(
                status=AlignmentStatus.FAILED,
                base_clock=ControllerType.TBOX,
                sources={c: _NULL_OFFSET for c in target_controllers},
                warnings=tuple(warnings),
            )

    base_anchors = by_ctrl.get(base, {})
    sources: dict[ControllerType, SourceOffset] = {}
    sources[base] = SourceOffset(
        offset=0.0,
        confidence=1.0,
        method=AlignmentMethod.NONE,
        sample_count=sum(len(v) for v in base_anchors.values()),
    )

    for ctrl in target_controllers:
        if ctrl == base:
            continue
        src_anchors = by_ctrl.get(ctrl, {})
        if not src_anchors:
            sources[ctrl] = _NULL_OFFSET
            warnings.append(f"{ctrl.value}: no usable anchors")
            continue

        direct = _direct_align(base_anchors, src_anchors)
        chosen: Optional[tuple[float, float, int, AlignmentMethod]] = None
        if direct is not None:
            off, conf, n = direct
            if _is_sane(off):
                chosen = (off, conf, n, AlignmentMethod.DIRECT)
            else:
                warnings.append(
                    f"{ctrl.value}: direct offset {off:.0f}s exceeds 30-day sanity ceiling — rejected"
                )
        sources[ctrl] = SourceOffset(
            offset=chosen[0] if chosen else None,
            confidence=chosen[1] if chosen else 0.0,
            method=chosen[3] if chosen else AlignmentMethod.NONE,
            sample_count=chosen[2] if chosen else 0,
        )

    bridge_off = sources.get(TWO_HOP_BRIDGE)
    if (
        bridge_off
        and bridge_off.offset is not None
        and bridge_off.confidence >= 0.6
        and TWO_HOP_BRIDGE != base
    ):
        bridge_anchors = by_ctrl.get(TWO_HOP_BRIDGE, {})
        for ctrl in target_controllers:
            if ctrl in (base, TWO_HOP_BRIDGE):
                continue
            current = sources[ctrl]
            if current.confidence >= 0.7:
                continue
            two_hop = _two_hop_align(
                bridge_anchors, by_ctrl.get(ctrl, {}), bridge_off.offset, bridge_off.confidence
            )
            if two_hop is None:
                continue
            off, conf, n = two_hop
            if not _is_sane(off):
                warnings.append(
                    f"{ctrl.value}: two-hop offset {off:.0f}s exceeds 30-day sanity ceiling — rejected"
                )
                continue
            if conf > current.confidence:
                sources[ctrl] = SourceOffset(
                    offset=off, confidence=conf, method=AlignmentMethod.TWO_HOP, sample_count=n
                )

    targets = [c for c in target_controllers if c != base]
    aligned = [c for c in targets if sources[c].offset is not None and sources[c].confidence >= SUCCESS_CONFIDENCE_FLOOR]
    if targets and len(aligned) == len(targets):
        status = AlignmentStatus.SUCCESS
    else:
        any_aligned = [c for c in targets if sources[c].offset is not None]
        if targets and len(any_aligned) >= max(1, math.ceil(len(targets) * PARTIAL_RATIO_FLOOR)):
            status = AlignmentStatus.PARTIAL
        elif not targets:
            status = AlignmentStatus.SUCCESS
        else:
            status = AlignmentStatus.FAILED

    if degraded_to_android and status == AlignmentStatus.SUCCESS:
        status = AlignmentStatus.PARTIAL

    return BundleAlignmentSummary(
        status=status,
        base_clock=base,
        sources=sources,
        warnings=tuple(warnings),
    )
