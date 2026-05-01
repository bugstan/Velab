from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import yaml
from pydantic import BaseModel, Field, field_validator

from log_pipeline.interfaces import ControllerType


class ContentSignature(BaseModel):
    magic_bytes: Optional[str] = None
    regex: Optional[str] = None

    @field_validator("regex")
    @classmethod
    def _compile_regex(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            re.compile(v)
        return v


class ControllerRule(BaseModel):
    type: ControllerType
    description: str = ""
    path_patterns: list[str] = Field(default_factory=list)
    name_patterns: list[str] = Field(default_factory=list)
    content_signatures: list[ContentSignature] = Field(default_factory=list)


class ClassifierConfig(BaseModel):
    controllers: list[ControllerRule]
    priority_order: list[ControllerType] = Field(default_factory=list)
    content_sniff_bytes: int = 8192


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a glob with `**` (cross-segment), `*`, `?`, `[...]` to a regex."""
    out: list[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                out.append(".*")
                i += 2
                if i < n and pattern[i] == "/":
                    i += 1
            else:
                out.append("[^/]*")
                i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "[":
            j = pattern.find("]", i + 1)
            if j == -1:
                out.append(re.escape(c))
                i += 1
            else:
                out.append(pattern[i : j + 1])
                i = j + 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


@dataclass(frozen=True)
class _CompiledRule:
    controller: ControllerType
    path_patterns: tuple[re.Pattern[str], ...]
    name_patterns: tuple[re.Pattern[str], ...]
    magic_bytes: tuple[bytes, ...]
    content_regexes: tuple[re.Pattern[bytes], ...]


class Classifier:
    def __init__(self, config: ClassifierConfig):
        self._config = config
        self._rules: list[_CompiledRule] = []
        for rule in self._ordered(config.controllers, config.priority_order):
            magics: list[bytes] = []
            regexes: list[re.Pattern[bytes]] = []
            for sig in rule.content_signatures:
                if sig.magic_bytes is not None:
                    magics.append(sig.magic_bytes.encode("latin-1"))
                if sig.regex is not None:
                    regexes.append(re.compile(sig.regex.encode("utf-8"), re.MULTILINE))
            self._rules.append(
                _CompiledRule(
                    controller=rule.type,
                    path_patterns=tuple(_glob_to_regex(p) for p in rule.path_patterns),
                    name_patterns=tuple(_glob_to_regex(p) for p in rule.name_patterns),
                    magic_bytes=tuple(magics),
                    content_regexes=tuple(regexes),
                )
            )

    @staticmethod
    def _ordered(
        rules: list[ControllerRule], priority: list[ControllerType]
    ) -> list[ControllerRule]:
        if not priority:
            return rules
        index = {t: i for i, t in enumerate(priority)}
        return sorted(rules, key=lambda r: index.get(r.type, len(priority)))

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Classifier":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        config = ClassifierConfig.model_validate(data)
        return cls(config)

    def classify(
        self,
        relative_path: str,
        file_path: Optional[Path] = None,
    ) -> ControllerType:
        """Classify a file given its path inside the bundle (POSIX-style relative).

        Priority: path → filename → content. Short-circuit on first hit.
        Returns ControllerType.UNKNOWN if no rule matches.
        """
        rel = relative_path.replace("\\", "/")
        name = rel.rsplit("/", 1)[-1]

        for rule in self._rules:
            if any(p.match(rel) for p in rule.path_patterns):
                return rule.controller

        for rule in self._rules:
            if any(p.match(name) for p in rule.name_patterns):
                return rule.controller

        if file_path is not None and file_path.is_file():
            head = self._read_head(file_path, self._config.content_sniff_bytes)
            for rule in self._rules:
                if any(head.startswith(m) for m in rule.magic_bytes):
                    return rule.controller
                if any(r.search(head) for r in rule.content_regexes):
                    return rule.controller

        return ControllerType.UNKNOWN

    @staticmethod
    def _read_head(path: Path, n: int) -> bytes:
        try:
            with open(path, "rb") as f:
                return f.read(n)
        except OSError:
            return b""

    def classify_many(
        self, items: Iterable[tuple[str, Optional[Path]]]
    ) -> list[tuple[str, ControllerType]]:
        return [(rel, self.classify(rel, fp)) for rel, fp in items]
