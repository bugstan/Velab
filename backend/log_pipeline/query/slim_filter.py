from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

from log_pipeline.interfaces import ControllerType


class SlimDropGroup(BaseModel):
    controller: ControllerType
    patterns: list[str] = Field(default_factory=list)


class SlimRulesSpec(BaseModel):
    drop: list[SlimDropGroup] = Field(default_factory=list)
    keep_always: list[str] = Field(default_factory=list)


@dataclass
class SlimFilter:
    """Dynamic-only line filter applied at query time.

    Decision precedence per line (matches CLAUDE.md §6.8):
      keep_always (any controller, any rule) > drop (controller-scoped) > pass-through.
    Compile once at startup; reuse across queries.
    """

    keep_always_patterns: tuple[re.Pattern[str], ...] = ()
    drop_per_controller: dict[ControllerType, tuple[re.Pattern[str], ...]] = field(
        default_factory=dict
    )

    @classmethod
    def from_yaml(cls, path: Path) -> "SlimFilter":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        spec = SlimRulesSpec.model_validate(data.get("slim", {}))
        keep = tuple(re.compile(p) for p in spec.keep_always)
        drop_map: dict[ControllerType, list[re.Pattern[str]]] = {}
        for group in spec.drop:
            drop_map.setdefault(group.controller, []).extend(re.compile(p) for p in group.patterns)
        return cls(
            keep_always_patterns=keep,
            drop_per_controller={k: tuple(v) for k, v in drop_map.items()},
        )

    @classmethod
    def empty(cls) -> "SlimFilter":
        return cls()

    def keep(self, controller: ControllerType, text: str) -> bool:
        for p in self.keep_always_patterns:
            if p.search(text):
                return True
        for p in self.drop_per_controller.get(controller, ()):
            if p.search(text):
                return False
        return True
