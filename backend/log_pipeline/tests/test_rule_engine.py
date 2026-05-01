from __future__ import annotations

from pathlib import Path

import yaml

from log_pipeline.interfaces import ControllerType
from log_pipeline.prescan.rule_engine import (
    PatternSpec,
    RuleEngine,
    RuleSpec,
    _strip_inner_named_groups,
)


def _engine(events: list[RuleSpec], anchors: list[RuleSpec] = ()) -> RuleEngine:
    return RuleEngine(events, list(anchors))


def test_regex_rule_fires_with_named_field():
    rule = RuleSpec(
        type="gear_shift",
        applies_to=[ControllerType.MCU],
        patterns=[PatternSpec(regex=r"GEAR\s*->\s*(?P<gear>[PRND])\b")],
        fields={"gear": {"from_group": "gear"}},
    )
    e = _engine([rule])
    hits = list(e.match(ControllerType.MCU, "GEAR -> D enabled"))
    assert len(hits) == 1
    assert hits[0].rule_kind == "event"
    assert hits[0].rule_type == "gear_shift"
    assert hits[0].fields == {"gear": "D"}


def test_regex_rule_with_separate_field_regex():
    rule = RuleSpec(
        type="system_reboot",
        applies_to=[ControllerType.ANDROID],
        patterns=[PatternSpec(regex=r"(?i)\b(reboot|restart)\b")],
        fields={"reason": {"regex": r"reason=([\w-]+)"}},
    )
    e = _engine([rule])
    hits = list(e.match(ControllerType.ANDROID, "system reboot reason=watchdog now"))
    assert len(hits) == 1
    assert hits[0].fields == {"reason": "watchdog"}


def test_keyword_any_rule_fires():
    rule = RuleSpec(
        type="charging_start",
        applies_to=[ControllerType.MCU],
        patterns=[PatternSpec(keyword_any=["charging started", "CHG_START"])],
    )
    e = _engine([rule])
    assert len(list(e.match(ControllerType.MCU, "Battery: charging started ok"))) == 1
    assert len(list(e.match(ControllerType.MCU, "CHG_START at 03:00"))) == 1
    assert len(list(e.match(ControllerType.MCU, "nothing relevant"))) == 0


def test_keyword_all_rule_requires_all_words():
    rule = RuleSpec(
        type="fota_download_start",
        applies_to=[ControllerType.FOTA],
        patterns=[PatternSpec(keyword_all=["FOTA", "download", "start"])],
    )
    e = _engine([rule])
    assert len(list(e.match(ControllerType.FOTA, "FOTA download start now"))) == 1
    assert len(list(e.match(ControllerType.FOTA, "FOTA download finished"))) == 0
    assert len(list(e.match(ControllerType.FOTA, "fota DOWNLOAD START"))) == 1  # ci


def test_rule_does_not_fire_for_other_controller():
    rule = RuleSpec(
        type="gear_shift",
        applies_to=[ControllerType.MCU],
        patterns=[PatternSpec(regex=r"GEAR\s*->\s*(?P<gear>[PRND])")],
    )
    e = _engine([rule])
    assert list(e.match(ControllerType.ANDROID, "GEAR -> D")) == []


def test_anchor_rule_carries_confidence():
    anchor = RuleSpec(
        type="tbox_clock_sync",
        applies_to=[ControllerType.TBOX],
        patterns=[PatternSpec(keyword_any=["rtc set hw", "ntp sync"])],
        confidence=0.98,
    )
    e = _engine([], [anchor])
    [hit] = list(e.match(ControllerType.TBOX, "info: rtc set hw ok"))
    assert hit.rule_kind == "anchor"
    assert hit.confidence == 0.98


def test_strip_inner_named_groups_idempotent():
    p = r"(?P<gear>[PRND])\b\s+(?P<rest>.+)"
    out = _strip_inner_named_groups(p)
    assert "?P<" not in out
    assert "(?:" in out


def test_engine_combines_multiple_rules_no_group_clash():
    rule_a = RuleSpec(
        type="gear_shift",
        applies_to=[ControllerType.MCU],
        patterns=[PatternSpec(regex=r"GEAR\s*->\s*(?P<gear>[PRND])")],
    )
    rule_b = RuleSpec(
        type="door_open",
        applies_to=[ControllerType.MCU],
        patterns=[PatternSpec(regex=r"DOOR_(?P<door>FL|FR)_OPEN")],
    )
    # combined regex must compile despite both having `<gear>` and `<door>` inner groups
    e = _engine([rule_a, rule_b])
    line = "GEAR -> P\nDOOR_FL_OPEN"
    types = sorted(h.rule_type for h in e.match(ControllerType.MCU, line))
    assert types == ["door_open", "gear_shift"]


def test_engine_loads_real_yaml_files(tmp_path: Path):
    events_yaml = tmp_path / "ev.yaml"
    anchors_yaml = tmp_path / "an.yaml"
    events_yaml.write_text(
        yaml.safe_dump(
            {
                "events": [
                    {
                        "type": "system_reboot",
                        "applies_to": ["android"],
                        "patterns": [{"regex": r"(?i)reboot"}],
                    }
                ]
            }
        )
    )
    anchors_yaml.write_text(
        yaml.safe_dump(
            {
                "anchors": [
                    {
                        "type": "system_boot",
                        "applies_to": ["android"],
                        "confidence": 0.9,
                        "patterns": [{"keyword_any": ["boot completed"]}],
                    }
                ]
            }
        )
    )
    e = RuleEngine.from_yaml_files(events_yaml, anchors_yaml)
    [evt] = list(e.match(ControllerType.ANDROID, "INFO: reboot now"))
    assert evt.rule_kind == "event" and evt.rule_type == "system_reboot"
    [anc] = list(e.match(ControllerType.ANDROID, "boot completed"))
    assert anc.rule_kind == "anchor" and anc.confidence == 0.9
