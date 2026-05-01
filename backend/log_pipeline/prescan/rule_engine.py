from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Literal, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError

from log_pipeline.interfaces import ControllerType

RuleKind = Literal["event", "anchor"]


class PatternSpec(BaseModel):
    regex: Optional[str] = None
    keyword_all: Optional[list[str]] = None
    keyword_any: Optional[list[str]] = None


class FieldSpec(BaseModel):
    regex: Optional[str] = None
    from_group: Optional[str] = None


class RuleSpec(BaseModel):
    type: str
    applies_to: list[ControllerType]
    patterns: list[PatternSpec] = Field(default_factory=list)
    fields: dict[str, FieldSpec] = Field(default_factory=dict)
    confidence: Optional[float] = None


class _Sub:
    """A single compiled sub-rule (one parent rule + one pattern)."""

    __slots__ = ("rule_idx", "kind", "regex", "keyword_all_words")

    def __init__(
        self,
        rule_idx: int,
        kind: Literal["regex", "keyword_any", "keyword_all"],
        regex: Optional[re.Pattern[str]] = None,
        keyword_all_words: Optional[tuple[str, ...]] = None,
    ):
        self.rule_idx = rule_idx
        self.kind = kind
        self.regex = regex
        self.keyword_all_words = keyword_all_words


@dataclass(frozen=True)
class RuleHit:
    rule_kind: RuleKind
    rule_type: str
    confidence: float
    fields: dict


@dataclass
class _Compiled:
    """Combined matcher state for one (controller, rule_kind) pair."""

    combined: Optional[re.Pattern[str]] = None
    group_to_sub: dict[str, _Sub] = field(default_factory=dict)
    keyword_all_subs: list[_Sub] = field(default_factory=list)
    individual_regex: dict[int, re.Pattern[str]] = field(default_factory=dict)


class RuleEngine:
    def __init__(self, event_specs: list[RuleSpec], anchor_specs: list[RuleSpec]):
        self._all_rules: list[tuple[RuleSpec, RuleKind]] = [
            *((s, "event") for s in event_specs),
            *((s, "anchor") for s in anchor_specs),
        ]
        # keyed by (controller, rule_kind) so an event and an anchor sharing a pattern
        # cannot shadow each other in a single combined `|` alternation
        self._per_ctrl_kind: dict[tuple[ControllerType, RuleKind], _Compiled] = {}
        self._compile()

    @classmethod
    def from_yaml_files(cls, event_yaml: Path, anchor_yaml: Path) -> "RuleEngine":
        events = _load_rules(event_yaml, "events")
        anchors = _load_rules(anchor_yaml, "anchors")
        return cls(events, anchors)

    def _compile(self) -> None:
        per_kind: dict[tuple[ControllerType, RuleKind], _Compiled] = {}
        for rule_idx, (spec, kind) in enumerate(self._all_rules):
            for ctrl in spec.applies_to:
                comp = per_kind.setdefault((ctrl, kind), _Compiled())
                first_regex = next((p.regex for p in spec.patterns if p.regex), None)
                if first_regex and rule_idx not in comp.individual_regex:
                    try:
                        comp.individual_regex[rule_idx] = re.compile(first_regex)
                    except re.error:
                        pass

                for p in spec.patterns:
                    if p.regex is not None:
                        gname = f"r{rule_idx}_{len(comp.group_to_sub)}"
                        comp.group_to_sub[gname] = _Sub(rule_idx=rule_idx, kind="regex")
                    elif p.keyword_any is not None:
                        gname = f"k{rule_idx}_{len(comp.group_to_sub)}"
                        comp.group_to_sub[gname] = _Sub(rule_idx=rule_idx, kind="keyword_any")
                    elif p.keyword_all is not None:
                        comp.keyword_all_subs.append(
                            _Sub(
                                rule_idx=rule_idx,
                                kind="keyword_all",
                                keyword_all_words=tuple(w.lower() for w in p.keyword_all),
                            )
                        )

        for (ctrl, kind), comp in per_kind.items():
            alts: list[str] = []
            for gname, sub in comp.group_to_sub.items():
                spec, _kind = self._all_rules[sub.rule_idx]
                if sub.kind == "regex":
                    pat = next(p.regex for p in spec.patterns if p.regex)
                    alts.append(f"(?P<{gname}>{_strip_inner_named_groups(pat)})")
                elif sub.kind == "keyword_any":
                    words = next(p.keyword_any for p in spec.patterns if p.keyword_any)
                    escaped = "|".join(re.escape(w) for w in words)
                    alts.append(f"(?P<{gname}>(?i:{escaped}))")
            if alts:
                try:
                    comp.combined = re.compile("|".join(alts))
                except re.error as e:
                    raise ValueError(
                        f"failed to compile combined regex for {ctrl}/{kind}: {e}"
                    ) from e
        self._per_ctrl_kind = per_kind

    def match(self, controller: ControllerType, text: str) -> Iterator[RuleHit]:
        for kind in ("event", "anchor"):
            comp = self._per_ctrl_kind.get((controller, kind))  # type: ignore[arg-type]
            if comp is None:
                continue
            if comp.combined is not None:
                for m in comp.combined.finditer(text):
                    for gname, value in m.groupdict().items():
                        if value is None:
                            continue
                        sub = comp.group_to_sub.get(gname)
                        if sub is None:
                            continue
                        yield self._build_hit(sub, comp, text)
                        break
            if comp.keyword_all_subs:
                text_lower = text.lower()
                for sub in comp.keyword_all_subs:
                    words = sub.keyword_all_words
                    if words and all(w in text_lower for w in words):
                        yield self._build_hit(sub, comp, text)

    def _build_hit(self, sub: _Sub, comp: _Compiled, text: str) -> RuleHit:
        spec, kind = self._all_rules[sub.rule_idx]
        fields = self._extract_fields(spec, comp, sub.rule_idx, text, None)
        confidence = (
            spec.confidence if spec.confidence is not None else (1.0 if kind == "event" else 0.5)
        )
        return RuleHit(rule_kind=kind, rule_type=spec.type, confidence=confidence, fields=fields)

    @staticmethod
    def _extract_fields(
        spec: RuleSpec,
        comp: _Compiled,
        rule_idx: int,
        text: str,
        main_match: Optional[re.Match[str]],
    ) -> dict:
        out: dict = {}
        if not spec.fields:
            return out
        ind_pat = comp.individual_regex.get(rule_idx)
        ind_match = ind_pat.search(text) if ind_pat else None
        for name, fs in spec.fields.items():
            if fs.from_group:
                target = ind_match
                if target is not None:
                    try:
                        v = target.group(fs.from_group)
                        if v is not None:
                            out[name] = v
                    except (IndexError, KeyError, error):  # type: ignore[name-defined]
                        pass
            elif fs.regex:
                try:
                    fm = re.search(fs.regex, text)
                except re.error:
                    continue
                if fm:
                    out[name] = fm.group(1) if fm.groups() else fm.group(0)
        return out


# helper exception alias to keep _extract_fields readable (re module exposes `error`)
error = re.error  # noqa: E305


def _load_rules(path: Path, top_key: str) -> list[RuleSpec]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    raw = data.get(top_key, [])
    out: list[RuleSpec] = []
    for entry in raw:
        try:
            out.append(RuleSpec.model_validate(entry))
        except ValidationError as e:
            raise ValueError(f"invalid rule in {path}: {entry!r}: {e}") from e
    return out


_INNER_NAMED_GROUP = re.compile(r"\(\?P<([A-Za-z_]\w*)>")
_LEADING_INLINE_FLAGS = re.compile(r"^\(\?([aiLmsux]+)\)")


def _strip_inner_named_groups(pattern: str) -> str:
    """Rewrite `(?P<name>...)` → `(?:...)` so combining rules can't redefine names.

    Also rewrites a leading global inline flag like ``(?i)`` to the scoped form
    ``(?i:...)`` because Python 3.11+ rejects global flags that aren't at the start
    of the *whole* combined pattern.
    """
    m = _LEADING_INLINE_FLAGS.match(pattern)
    if m:
        flags = m.group(1)
        pattern = f"(?{flags}:{pattern[m.end():]})"
    return _INNER_NAMED_GROUP.sub("(?:", pattern)
