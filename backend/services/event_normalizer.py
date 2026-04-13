"""Event normalizer based on real vehicle log semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import re


class EventCategory(str, Enum):
    FOTA_LIFECYCLE = "fota_lifecycle"
    SYSTEM_STATE = "system_state"
    ERROR = "error"
    NETWORK = "network"
    POWER = "power"
    DIAGNOSTIC = "diagnostic"
    UNKNOWN = "unknown"


class FotaStage(str, Enum):
    INIT = "init"
    DOWNLOAD = "download"
    VERIFY = "verify"
    INSTALL = "install"
    REBOOT = "reboot"
    COMPLETE = "complete"
    FAILED = "failed"


class ErrorSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class NormalizedEvent:
    case_id: str
    file_id: str
    source_type: str
    normalized_ts: datetime
    original_ts: datetime
    clock_confidence: float
    category: EventCategory
    event_type: str
    severity: ErrorSeverity
    module: str
    message: str
    raw_content: str
    fota_stage: Optional[FotaStage] = None
    fota_version: Optional[str] = None
    fota_progress: Optional[float] = None
    error_code: Optional[str] = None
    stack_trace: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class EventNormalizer:
    def __init__(self):
        self.noise_patterns = [
            re.compile(r"^\s*$"),
            re.compile(r"heartbeat", re.IGNORECASE),
            re.compile(r"^#"),
        ]

    def normalize_event(
        self,
        parsed_event: Dict[str, Any],
        case_id: str,
        file_id: str,
        normalized_ts: datetime,
        clock_confidence: float,
    ) -> Optional[NormalizedEvent]:
        if self._is_noise(parsed_event):
            return None

        message = parsed_event.get("message", "")
        module = parsed_event.get("module") or parsed_event.get("tag") or "unknown"
        source_type = parsed_event.get("source_type", "unknown")
        original_ts = parsed_event.get("timestamp") or parsed_event.get("original_ts") or normalized_ts
        level = (parsed_event.get("level") or "INFO").upper()

        category = self._classify_category(message, module)
        severity = self._determine_severity(level, message)
        fota_stage = self._identify_fota_stage(message)

        return NormalizedEvent(
            case_id=case_id,
            file_id=file_id,
            source_type=source_type,
            normalized_ts=normalized_ts,
            original_ts=original_ts,
            clock_confidence=clock_confidence,
            category=category,
            event_type=self._extract_event_type(message, category),
            severity=severity,
            module=module,
            message=message,
            raw_content=parsed_event.get("raw") or parsed_event.get("raw_snippet") or "",
            fota_stage=fota_stage,
            fota_version=self._extract_version(message),
            fota_progress=self._extract_progress(message),
            error_code=self._extract_error_code(message),
            stack_trace=parsed_event.get("stack_trace"),
            tags=self._generate_tags(category, fota_stage, severity, module),
            metadata={k: v for k, v in {
                "tag": parsed_event.get("tag"),
                "pid": parsed_event.get("pid"),
                "tid": parsed_event.get("tid"),
                "source_file": (parsed_event.get("parsed_fields") or {}).get("source_file")
                if isinstance(parsed_event.get("parsed_fields"), dict) else None,
            }.items() if v is not None},
        )

    def normalize_batch(
        self,
        parsed_events: List[Dict[str, Any]],
        case_id: str,
        file_id: str,
        time_alignment_result: Dict[str, Any],
    ) -> List[NormalizedEvent]:
        result: List[NormalizedEvent] = []
        offsets = time_alignment_result.get("offsets", {})

        for event in parsed_events:
            source_type = event.get("source_type", "unknown")
            source_offset = offsets.get(source_type, {})
            confidence = source_offset.get("confidence", 1.0)
            normalized_ts = event.get("normalized_ts") or event.get("timestamp") or datetime.now()
            normalized = self.normalize_event(
                parsed_event=event,
                case_id=case_id,
                file_id=file_id,
                normalized_ts=normalized_ts,
                clock_confidence=confidence,
            )
            if normalized:
                result.append(normalized)
        return result

    def _is_noise(self, event: Dict[str, Any]) -> bool:
        message = event.get("message", "")
        raw = event.get("raw", "")
        return any(p.search(message) or p.search(raw) for p in self.noise_patterns)

    def _classify_category(self, message: str, module: str) -> EventCategory:
        msg = message.lower()
        mod = module.lower()

        if any(k in msg for k in ["fota", "upgrade", "showupgraderesult", "onmcuindication", "fotamode"]):
            return EventCategory.FOTA_LIFECYCLE
        if any(k in msg for k in ["icgmlinknotify", "modem", "network", "socket", "linksts"]):
            return EventCategory.NETWORK
        if any(k in msg for k in ["sys date", "oncreate", "boot", "init", "reset"]):
            return EventCategory.SYSTEM_STATE
        if any(k in msg for k in ["battery", "voltage", "power"]):
            return EventCategory.POWER
        if any(k in msg for k in ["error", "fail", "panic", "exception"]):
            return EventCategory.ERROR
        if any(k in msg for k in ["diag", "trace", "dtc"]):
            return EventCategory.DIAGNOSTIC
        if "fota" in mod:
            return EventCategory.FOTA_LIFECYCLE
        return EventCategory.UNKNOWN

    @staticmethod
    def _extract_event_type(message: str, category: EventCategory) -> str:
        msg = message.lower()
        if category == EventCategory.FOTA_LIFECYCLE:
            if "download" in msg:
                return "fota_download"
            if "verify" in msg or "signature" in msg:
                return "fota_verify"
            if "install" in msg or "flash" in msg:
                return "fota_install"
            return "fota_general"
        if category == EventCategory.NETWORK:
            return "network_link"
        if category == EventCategory.ERROR:
            return "error_general"
        return category.value

    def _determine_severity(self, level: str, message: str) -> ErrorSeverity:
        msg = message.lower()
        if level in {"FATAL", "CRITICAL"} or any(k in msg for k in ["panic", "fatal", "crash"]):
            return ErrorSeverity.CRITICAL
        if level == "ERROR" or any(k in msg for k in ["error", "failed", "exception"]):
            return ErrorSeverity.HIGH
        if level in {"WARN", "WARNING"} or any(k in msg for k in ["timeout", "retry", "warn"]):
            return ErrorSeverity.MEDIUM
        if level in {"INFO", "NOTICE"}:
            return ErrorSeverity.INFO
        if level == "DEBUG":
            return ErrorSeverity.INFO
        return ErrorSeverity.LOW

    def _identify_fota_stage(self, message: str) -> Optional[FotaStage]:
        msg = message.lower()
        if any(k in msg for k in ["service oncreate", "fotamode", "onmcuindication"]):
            return FotaStage.INIT
        if any(k in msg for k in ["download", "refreshprogress", "progress"]):
            return FotaStage.DOWNLOAD
        if any(k in msg for k in ["verify", "signature"]):
            return FotaStage.VERIFY
        if any(k in msg for k in ["install", "flash", "writing"]):
            return FotaStage.INSTALL
        if "reboot" in msg:
            return FotaStage.REBOOT
        if any(k in msg for k in ["showupgraderesult", "upgradeflag : idle", "success"]):
            return FotaStage.COMPLETE
        if any(k in msg for k in ["failed", "fail", "abort", "error"]):
            return FotaStage.FAILED
        return None

    @staticmethod
    def _extract_version(message: str) -> Optional[str]:
        patterns = [
            r"version[:=\s]+([0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?)",
            r"\bv([0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?)\b",
        ]
        for p in patterns:
            m = re.search(p, message, re.IGNORECASE)
            if m:
                return m.group(1)
        return None

    @staticmethod
    def _extract_progress(message: str) -> Optional[float]:
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", message)
        if m:
            return float(m.group(1))
        m = re.search(r"refreshProgress\s*=\s*(\d+(?:\.\d+)?)", message, re.IGNORECASE)
        if m:
            return float(m.group(1))
        return None

    @staticmethod
    def _extract_error_code(message: str) -> Optional[str]:
        for p in [r"error[_\s]code[:=\s]+([A-Z0-9_-]+)", r"\[([A-Z]{2,}[_0-9-]+)\]"]:
            m = re.search(p, message, re.IGNORECASE)
            if m:
                return m.group(1)
        return None

    @staticmethod
    def _generate_tags(
        category: EventCategory,
        fota_stage: Optional[FotaStage],
        severity: ErrorSeverity,
        module: str,
    ) -> List[str]:
        tags = [category.value, f"module_{module.lower()}"]
        if fota_stage:
            tags.append(f"fota_{fota_stage.value}")
        if severity in (ErrorSeverity.CRITICAL, ErrorSeverity.HIGH):
            tags.append("high_priority")
        return tags
