"""
Parser Service 基础类和接口定义

定义了所有日志解析器必须遵循的统一接口，确保不同格式的日志
都能被转换为标准化的事件模型。

作者：FOTA 诊断平台团队
创建时间：2026-04-03
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List, Iterator
from pathlib import Path


class EventLevel(str, Enum):
    """事件级别枚举"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"


class EventType(str, Enum):
    """事件类型枚举"""
    LOG = "LOG"  # 普通日志
    ERROR = "ERROR"  # 错误事件
    WARNING = "WARNING"  # 警告事件
    STATE_CHANGE = "STATE_CHANGE"  # 状态变更
    FOTA_STAGE = "FOTA_STAGE"  # FOTA 阶段转换
    NETWORK = "NETWORK"  # 网络事件
    FILE_IO = "FILE_IO"  # 文件IO事件
    SYSTEM = "SYSTEM"  # 系统事件


@dataclass
class ParsedEvent:
    """
    解析后的标准化事件模型
    
    所有解析器输出的事件都必须符合这个统一结构，
    以便后续的时间对齐和事件归一化处理。
    """
    # 必填字段
    source_type: str  # android / kernel / fota / dlt / mcu / ibdu / vehicle_signal
    original_ts: Optional[datetime]  # 原始时间戳（可能为None，如MCU相对时间）
    message: str  # 日志消息内容
    raw_line_number: int  # 原始日志行号
    
    # 可选字段
    event_type: EventType = EventType.LOG
    level: EventLevel = EventLevel.INFO
    module: Optional[str] = None  # 模块名称（如 FotaDownloadImpl）
    thread: Optional[str] = None  # 线程ID或名称
    process: Optional[str] = None  # 进程ID或名称
    tag: Optional[str] = None  # 日志标签（Android logcat）
    
    # 原始日志片段（用于回溯）
    raw_snippet: Optional[str] = None  # 原始行内容
    
    # 结构化解析字段（因日志类型而异）
    parsed_fields: Dict[str, Any] = field(default_factory=dict)
    
    # 解析器元数据
    parser_name: str = ""
    parser_version: str = "1.0.0"
    parse_confidence: float = 1.0  # 解析置信度 (0.0-1.0)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，用于数据库存储"""
        return {
            "source_type": self.source_type,
            "original_ts": self.original_ts.isoformat() if self.original_ts else None,
            "message": self.message,
            "raw_line_number": self.raw_line_number,
            "event_type": self.event_type.value,
            "level": self.level.value,
            "module": self.module,
            "thread": self.thread,
            "process": self.process,
            "tag": self.tag,
            "raw_snippet": self.raw_snippet,
            "parsed_fields": self.parsed_fields,
            "parser_name": self.parser_name,
            "parser_version": self.parser_version,
            "parse_confidence": self.parse_confidence,
        }


class BaseParser(ABC):
    """
    日志解析器基类
    
    所有具体的解析器（Android、FOTA、MCU等）都必须继承此类
    并实现 parse_file 方法。
    
    设计原则：
    1. 流式处理：逐行解析，避免一次性加载整个文件到内存
    2. 容错性：单行解析失败不应影响其他行
    3. 性能：支持时间窗口裁剪，跳过窗口外的日志
    """
    
    def __init__(self, source_type: str, parser_name: str, parser_version: str = "1.0.0"):
        """
        初始化解析器
        
        Args:
            source_type: 日志来源类型（android/fota/mcu等）
            parser_name: 解析器名称
            parser_version: 解析器版本号
        """
        self.source_type = source_type
        self.parser_name = parser_name
        self.parser_version = parser_version
    
    @abstractmethod
    def parse_file(
        self,
        file_path: Path,
        time_window: Optional[tuple[datetime, datetime]] = None,
        max_lines: Optional[int] = None
    ) -> Iterator[ParsedEvent]:
        """
        解析日志文件（流式处理）
        
        Args:
            file_path: 日志文件路径
            time_window: 可选的时间窗口 (start_time, end_time)，
                        仅解析此窗口内的日志（快速通道优化）
            max_lines: 可选的最大解析行数限制
        
        Yields:
            ParsedEvent: 解析后的标准化事件
        
        Raises:
            FileNotFoundError: 文件不存在
            PermissionError: 无权限读取文件
            ValueError: 文件格式不支持
        """
        pass
    
    def _should_skip_line(
        self,
        line_ts: Optional[datetime],
        time_window: Optional[tuple[datetime, datetime]]
    ) -> bool:
        """
        判断是否应跳过当前行（时间窗口裁剪优化）
        
        Args:
            line_ts: 当前行的时间戳
            time_window: 时间窗口
        
        Returns:
            bool: True表示应跳过，False表示应解析
        """
        if time_window is None or line_ts is None:
            return False
        
        start_time, end_time = time_window
        return line_ts < start_time or line_ts > end_time
    
    def _create_event(
        self,
        message: str,
        raw_line_number: int,
        original_ts: Optional[datetime] = None,
        **kwargs
    ) -> ParsedEvent:
        """
        创建标准化事件对象（辅助方法）
        
        Args:
            message: 日志消息
            raw_line_number: 原始行号
            original_ts: 原始时间戳
            **kwargs: 其他可选字段
        
        Returns:
            ParsedEvent: 标准化事件对象
        """
        return ParsedEvent(
            source_type=self.source_type,
            original_ts=original_ts,
            message=message,
            raw_line_number=raw_line_number,
            parser_name=self.parser_name,
            parser_version=self.parser_version,
            **kwargs
        )


class ParserRegistry:
    """
    解析器注册表
    
    管理所有可用的解析器，支持根据文件类型自动选择合适的解析器。
    """
    
    def __init__(self):
        self._parsers: Dict[str, type[BaseParser]] = {}
    
    def register(self, source_type: str, parser_class: type[BaseParser]):
        """
        注册解析器
        
        Args:
            source_type: 日志来源类型
            parser_class: 解析器类
        """
        self._parsers[source_type] = parser_class
    
    def get_parser(self, source_type: str) -> Optional[BaseParser]:
        """
        获取解析器实例
        
        Args:
            source_type: 日志来源类型
        
        Returns:
            BaseParser: 解析器实例，如果未注册则返回None
        """
        parser_class = self._parsers.get(source_type)
        if parser_class:
            return parser_class()
        return None
    
    def list_supported_types(self) -> List[str]:
        """
        列出所有支持的日志类型
        
        Returns:
            List[str]: 支持的日志类型列表
        """
        return list(self._parsers.keys())


# 全局解析器注册表实例
registry = ParserRegistry()
