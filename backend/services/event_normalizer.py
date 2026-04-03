"""
Event Normalizer Service

职责：
1. 语义归一化：统一不同来源的日志格式
2. 降噪：过滤无关日志
3. 事件分类：识别FOTA阶段、错误类型等
4. 标准化输出：生成统一的事件模型

输入：ParsedEvent（来自Parser Service）
输出：NormalizedEvent（写入diagnosis_events表）
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
import re


class EventCategory(str, Enum):
    """事件分类"""
    FOTA_LIFECYCLE = "fota_lifecycle"  # FOTA生命周期事件
    SYSTEM_STATE = "system_state"      # 系统状态变化
    ERROR = "error"                     # 错误事件
    NETWORK = "network"                 # 网络事件
    STORAGE = "storage"                 # 存储事件
    POWER = "power"                     # 电源事件
    DIAGNOSTIC = "diagnostic"           # 诊断相关
    UNKNOWN = "unknown"                 # 未分类


class FotaStage(str, Enum):
    """FOTA阶段"""
    INIT = "init"
    VERSION_CHECK = "version_check"
    DOWNLOAD = "download"
    VERIFY = "verify"
    INSTALL = "install"
    REBOOT = "reboot"
    ROLLBACK = "rollback"
    COMPLETE = "complete"
    FAILED = "failed"


class ErrorSeverity(str, Enum):
    """错误严重程度"""
    CRITICAL = "critical"  # 致命错误，导致流程中断
    HIGH = "high"          # 高危错误，可能影响功能
    MEDIUM = "medium"      # 中等错误，部分功能受影响
    LOW = "low"            # 低级错误，不影响主流程
    INFO = "info"          # 信息性日志


@dataclass
class NormalizedEvent:
    """标准化事件模型（对应diagnosis_events表）"""
    # 基础字段
    case_id: str
    file_id: str
    source_type: str
    normalized_ts: datetime
    original_ts: datetime
    clock_confidence: float
    
    # 事件分类
    category: EventCategory
    event_type: str
    severity: ErrorSeverity
    
    # 内容字段
    module: str
    message: str
    raw_content: str
    
    # FOTA特定字段
    fota_stage: Optional[FotaStage] = None
    fota_version: Optional[str] = None
    fota_progress: Optional[float] = None
    
    # 错误字段
    error_code: Optional[str] = None
    stack_trace: Optional[str] = None
    
    # 元数据
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class EventNormalizer:
    """事件标准化服务"""
    
    def __init__(self):
        # FOTA关键词模式
        self.fota_patterns = {
            FotaStage.INIT: [
                r'fota.*init',
                r'update.*start',
                r'ota.*begin'
            ],
            FotaStage.VERSION_CHECK: [
                r'version.*check',
                r'check.*version',
                r'query.*version'
            ],
            FotaStage.DOWNLOAD: [
                r'download.*start',
                r'downloading',
                r'download.*package',
                r'fetch.*package'
            ],
            FotaStage.VERIFY: [
                r'verify.*package',
                r'checksum',
                r'signature.*check'
            ],
            FotaStage.INSTALL: [
                r'install.*start',
                r'installing',
                r'apply.*update'
            ],
            FotaStage.REBOOT: [
                r'reboot',
                r'restart',
                r'system.*boot'
            ],
            FotaStage.ROLLBACK: [
                r'rollback',
                r'restore.*previous',
                r'revert.*version'
            ],
            FotaStage.COMPLETE: [
                r'fota.*complete',
                r'update.*success',
                r'ota.*finish'
            ],
            FotaStage.FAILED: [
                r'fota.*fail',
                r'update.*error',
                r'ota.*abort'
            ]
        }
        
        # 错误关键词
        self.error_patterns = {
            ErrorSeverity.CRITICAL: [
                r'fatal',
                r'crash',
                r'panic',
                r'abort'
            ],
            ErrorSeverity.HIGH: [
                r'error',
                r'fail',
                r'exception'
            ],
            ErrorSeverity.MEDIUM: [
                r'warn',
                r'timeout',
                r'retry'
            ],
            ErrorSeverity.LOW: [
                r'notice',
                r'skip'
            ]
        }
        
        # 噪音过滤规则（这些日志通常不重要）
        self.noise_patterns = [
            r'^DEBUG.*heartbeat',
            r'^VERBOSE.*',
            r'^\s*$',  # 空行
            r'^#',     # 注释行
        ]
        
        # 编译正则表达式
        self._compile_patterns()
    
    def _compile_patterns(self):
        """预编译正则表达式以提高性能"""
        self.compiled_fota = {
            stage: [re.compile(p, re.IGNORECASE) for p in patterns]
            for stage, patterns in self.fota_patterns.items()
        }
        
        self.compiled_errors = {
            severity: [re.compile(p, re.IGNORECASE) for p in patterns]
            for severity, patterns in self.error_patterns.items()
        }
        
        self.compiled_noise = [
            re.compile(p, re.IGNORECASE) for p in self.noise_patterns
        ]
    
    def normalize_event(
        self,
        parsed_event: Dict[str, Any],
        case_id: str,
        file_id: str,
        normalized_ts: datetime,
        clock_confidence: float
    ) -> Optional[NormalizedEvent]:
        """
        标准化单个事件
        
        Args:
            parsed_event: 来自Parser的原始事件
            case_id: 案件ID
            file_id: 文件ID
            normalized_ts: 标准化时间戳
            clock_confidence: 时钟置信度
        
        Returns:
            NormalizedEvent或None（如果是噪音）
        """
        # 降噪：过滤无关日志
        if self._is_noise(parsed_event):
            return None
        
        # 提取基础字段
        source_type = parsed_event.get('source_type', 'unknown')
        original_ts = parsed_event.get('timestamp')
        module = parsed_event.get('module', 'unknown')
        message = parsed_event.get('message', '')
        raw_content = parsed_event.get('raw', '')
        level = parsed_event.get('level', 'INFO')
        
        # 事件分类
        category = self._classify_category(message, module)
        event_type = self._extract_event_type(message, category)
        severity = self._determine_severity(level, message)
        
        # FOTA特定字段
        fota_stage = self._identify_fota_stage(message)
        fota_version = self._extract_version(message)
        fota_progress = self._extract_progress(message)
        
        # 错误字段
        error_code = self._extract_error_code(message)
        stack_trace = parsed_event.get('stack_trace')
        
        # 标签生成
        tags = self._generate_tags(
            category, fota_stage, severity, module
        )
        
        # 元数据
        metadata = {
            'pid': parsed_event.get('pid'),
            'tid': parsed_event.get('tid'),
            'tag': parsed_event.get('tag'),
            'filename': parsed_event.get('filename'),
        }
        # 移除None值
        metadata = {k: v for k, v in metadata.items() if v is not None}
        
        return NormalizedEvent(
            case_id=case_id,
            file_id=file_id,
            source_type=source_type,
            normalized_ts=normalized_ts,
            original_ts=original_ts,
            clock_confidence=clock_confidence,
            category=category,
            event_type=event_type,
            severity=severity,
            module=module,
            message=message,
            raw_content=raw_content,
            fota_stage=fota_stage,
            fota_version=fota_version,
            fota_progress=fota_progress,
            error_code=error_code,
            stack_trace=stack_trace,
            tags=tags,
            metadata=metadata
        )
    
    def _is_noise(self, event: Dict[str, Any]) -> bool:
        """判断是否为噪音日志"""
        message = event.get('message', '')
        raw = event.get('raw', '')
        
        for pattern in self.compiled_noise:
            if pattern.search(message) or pattern.search(raw):
                return True
        
        return False
    
    def _classify_category(self, message: str, module: str) -> EventCategory:
        """分类事件类别"""
        msg_lower = message.lower()
        mod_lower = module.lower()
        
        # FOTA相关
        if any(kw in msg_lower or kw in mod_lower 
               for kw in ['fota', 'ota', 'update', 'upgrade']):
            return EventCategory.FOTA_LIFECYCLE
        
        # 网络相关
        if any(kw in msg_lower 
               for kw in ['network', 'connect', 'socket', 'http', 'download']):
            return EventCategory.NETWORK
        
        # 存储相关
        if any(kw in msg_lower 
               for kw in ['storage', 'disk', 'file', 'mount', 'partition']):
            return EventCategory.STORAGE
        
        # 电源相关
        if any(kw in msg_lower 
               for kw in ['power', 'battery', 'voltage', 'suspend']):
            return EventCategory.POWER
        
        # 系统状态
        if any(kw in msg_lower 
               for kw in ['boot', 'init', 'shutdown', 'reboot']):
            return EventCategory.SYSTEM_STATE
        
        # 错误
        if any(kw in msg_lower 
               for kw in ['error', 'fail', 'exception', 'crash']):
            return EventCategory.ERROR
        
        # 诊断
        if any(kw in msg_lower 
               for kw in ['diag', 'debug', 'trace', 'dump']):
            return EventCategory.DIAGNOSTIC
        
        return EventCategory.UNKNOWN
    
    def _extract_event_type(self, message: str, category: EventCategory) -> str:
        """提取具体事件类型"""
        msg_lower = message.lower()
        
        # 根据类别提取更具体的类型
        if category == EventCategory.FOTA_LIFECYCLE:
            if 'download' in msg_lower:
                return 'fota_download'
            elif 'install' in msg_lower:
                return 'fota_install'
            elif 'verify' in msg_lower:
                return 'fota_verify'
            return 'fota_general'
        
        elif category == EventCategory.NETWORK:
            if 'connect' in msg_lower:
                return 'network_connect'
            elif 'disconnect' in msg_lower:
                return 'network_disconnect'
            return 'network_general'
        
        elif category == EventCategory.ERROR:
            if 'timeout' in msg_lower:
                return 'error_timeout'
            elif 'permission' in msg_lower:
                return 'error_permission'
            return 'error_general'
        
        return category.value
    
    def _determine_severity(self, level: str, message: str) -> ErrorSeverity:
        """确定严重程度"""
        msg_lower = message.lower()
        
        # 先检查消息内容中的关键词
        for severity, patterns in self.compiled_errors.items():
            for pattern in patterns:
                if pattern.search(msg_lower):
                    return severity
        
        # 根据日志级别判断
        level_upper = level.upper()
        if level_upper in ['FATAL', 'CRITICAL']:
            return ErrorSeverity.CRITICAL
        elif level_upper in ['ERROR']:
            return ErrorSeverity.HIGH
        elif level_upper in ['WARN', 'WARNING']:
            return ErrorSeverity.MEDIUM
        elif level_upper in ['INFO', 'NOTICE']:
            return ErrorSeverity.INFO
        
        return ErrorSeverity.LOW
    
    def _identify_fota_stage(self, message: str) -> Optional[FotaStage]:
        """识别FOTA阶段"""
        msg_lower = message.lower()
        
        for stage, patterns in self.compiled_fota.items():
            for pattern in patterns:
                if pattern.search(msg_lower):
                    return stage
        
        return None
    
    def _extract_version(self, message: str) -> Optional[str]:
        """提取版本号"""
        # 匹配常见版本号格式
        patterns = [
            r'version[:\s]+([0-9]+\.[0-9]+\.[0-9]+)',
            r'v([0-9]+\.[0-9]+\.[0-9]+)',
            r'([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def _extract_progress(self, message: str) -> Optional[float]:
        """提取进度百分比"""
        # 匹配百分比
        match = re.search(r'(\d+(?:\.\d+)?)\s*%', message)
        if match:
            return float(match.group(1))
        
        # 匹配分数形式 (e.g., "50/100")
        match = re.search(r'(\d+)\s*/\s*(\d+)', message)
        if match:
            current = float(match.group(1))
            total = float(match.group(2))
            if total > 0:
                return (current / total) * 100.0
        
        return None
    
    def _extract_error_code(self, message: str) -> Optional[str]:
        """提取错误码"""
        # 匹配常见错误码格式
        patterns = [
            r'error[_\s]code[:\s]+([A-Z0-9_-]+)',
            r'err[:\s]+([A-Z0-9_-]+)',
            r'code[:\s]+([A-Z0-9_-]+)',
            r'\[([A-Z0-9_-]+)\]',  # [ERROR_CODE]
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def _generate_tags(
        self,
        category: EventCategory,
        fota_stage: Optional[FotaStage],
        severity: ErrorSeverity,
        module: str
    ) -> List[str]:
        """生成标签"""
        tags = [category.value]
        
        if fota_stage:
            tags.append(f"fota_{fota_stage.value}")
        
        if severity in [ErrorSeverity.CRITICAL, ErrorSeverity.HIGH]:
            tags.append("high_priority")
        
        if module and module != 'unknown':
            tags.append(f"module_{module.lower()}")
        
        return tags
    
    def normalize_batch(
        self,
        parsed_events: List[Dict[str, Any]],
        case_id: str,
        file_id: str,
        time_alignment_result: Dict[str, Any]
    ) -> List[NormalizedEvent]:
        """
        批量标准化事件
        
        Args:
            parsed_events: 解析后的事件列表
            case_id: 案件ID
            file_id: 文件ID
            time_alignment_result: 时间对齐结果
        
        Returns:
            标准化事件列表
        """
        normalized_events = []
        
        for event in parsed_events:
            # 获取标准化时间戳
            normalized_ts = self._get_normalized_timestamp(
                event, time_alignment_result
            )
            
            # 获取时钟置信度
            source_type = event.get('source_type', 'unknown')
            clock_confidence = time_alignment_result.get(
                'offsets', 
            ).get(source_type, {}).get('confidence', 1.0)
            
            # 标准化事件
            normalized = self.normalize_event(
                event, case_id, file_id, normalized_ts, clock_confidence
            )
            
            if normalized:  # 过滤掉噪音
                normalized_events.append(normalized)
        
        return normalized_events
    
    def _get_normalized_timestamp(
        self,
        event: Dict[str, Any],
        time_alignment_result: Dict[str, Any]
    ) -> datetime:
        """获取标准化时间戳"""
        # 如果时间对齐结果中有normalized_ts，直接使用
        if 'normalized_ts' in event:
            return event['normalized_ts']
        
        # 否则使用原始时间戳
        return event.get('timestamp', datetime.now())
