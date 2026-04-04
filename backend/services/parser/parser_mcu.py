"""
MCU Log Parser

解析MCU（微控制器）日志
特点：
- 通常使用相对时间戳（uptime）
- 简单的文本格式
- 包含模块标识和日志级别
"""

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Iterator
from base import BaseParser, ParsedEvent, EventLevel, EventType


class MCUParser(BaseParser):
    """MCU日志解析器"""
    
    def __init__(self):
        super().__init__(
            source_type="mcu",
            parser_name="parser_mcu",
            parser_version="1.0.0"
        )
        
        # MCU log格式示例:
        # [12345] [INFO] [MODULE] message
        # 12345.678 I MODULE: message
        # +12345ms [MODULE] message
        
        # 格式1: [timestamp] [level] [module] message
        self.format1_pattern = re.compile(
            r'^\[(\d+(?:\.\d+)?)\]\s*'  # timestamp
            r'\[([A-Z]+)\]\s*'  # level
            r'\[([^\]]+)\]\s*'  # module
            r'(.+)$'  # message
        )
        
        # 格式2: timestamp level module: message
        self.format2_pattern = re.compile(
            r'^(\d+(?:\.\d+)?)\s+'  # timestamp
            r'([A-Z])\s+'  # level (single char)
            r'([A-Za-z0-9_]+):\s*'  # module
            r'(.+)$'  # message
        )
        
        # 格式3: +timestamp [module] message
        self.format3_pattern = re.compile(
            r'^\+(\d+)ms\s+'  # timestamp in ms
            r'\[([^\]]+)\]\s*'  # module
            r'(.+)$'  # message
        )
        
        # Level mapping
        self.level_map = {
            'F': EventLevel.FATAL,
            'FATAL': EventLevel.FATAL,
            'E': EventLevel.ERROR,
            'ERROR': EventLevel.ERROR,
            'W': EventLevel.WARN,
            'WARN': EventLevel.WARN,
            'WARNING': EventLevel.WARN,
            'I': EventLevel.INFO,
            'INFO': EventLevel.INFO,
            'D': EventLevel.DEBUG,
            'DEBUG': EventLevel.DEBUG,
            'V': EventLevel.DEBUG,
            'VERBOSE': EventLevel.DEBUG,
        }
        
        # 基准时间（用于相对时间转换）
        self.base_time = datetime.now()
    
    def parse_file(
        self,
        file_path: Path,
        time_window: Optional[tuple[datetime, datetime]] = None,
        max_lines: Optional[int] = None
    ) -> Iterator[ParsedEvent]:
        """解析MCU日志文件"""
        if not file_path.exists():
            raise FileNotFoundError(f"日志文件不存在: {file_path}")
        
        line_number = 0
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line_number += 1
                line = line.rstrip('\n\r')
                
                if not line.strip():
                    continue
                
                event = self.parse_line(line, line_number)
                
                if event:
                    if self._should_skip_line(event.original_ts, time_window):
                        continue
                    yield event
                
                if max_lines and line_number >= max_lines:
                    break
    
    def parse_line(
        self,
        line: str,
        line_number: int,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[ParsedEvent]:
        """解析单行日志"""
        if not line.strip():
            return None
        
        # 尝试格式1
        match = self.format1_pattern.match(line)
        if match:
            timestamp_sec = float(match.group(1))
            level_str = match.group(2)
            module = match.group(3)
            message = match.group(4).strip()
            
            # 转换相对时间为绝对时间
            timestamp = self.base_time + timedelta(seconds=timestamp_sec)
            
            # 确定日志级别
            level = self.level_map.get(level_str, EventLevel.INFO)
            
            # 确定事件类型
            event_type = self._determine_event_type(message, level)
            
            return self._create_event(
                original_ts=timestamp,                level=level,
                event_type=event_type,
                module=module,
                message=message,
                raw_snippet=line,
                raw_line_number=line_number,
                parsed_fields={'uptime_seconds': timestamp_sec}
            )
        
        # 尝试格式2
        match = self.format2_pattern.match(line)
        if match:
            timestamp_sec = float(match.group(1))
            level_char = match.group(2)
            module = match.group(3)
            message = match.group(4).strip()
            
            timestamp = self.base_time + timedelta(seconds=timestamp_sec)
            level = self.level_map.get(level_char, EventLevel.INFO)
            event_type = self._determine_event_type(message, level)
            
            return self._create_event(
                original_ts=timestamp,                level=level,
                event_type=event_type,
                module=module,
                message=message,
                raw_snippet=line,
                raw_line_number=line_number,
                parsed_fields={'uptime_seconds': timestamp_sec}
            )
        
        # 尝试格式3
        match = self.format3_pattern.match(line)
        if match:
            timestamp_ms = int(match.group(1))
            module = match.group(2)
            message = match.group(3).strip()
            
            timestamp = self.base_time + timedelta(milliseconds=timestamp_ms)
            
            # 从消息推断级别
            level = self._infer_level_from_message(message)
            event_type = self._determine_event_type(message, level)
            
            return self._create_event(
                original_ts=timestamp,                level=level,
                event_type=event_type,
                module=module,
                message=message,
                raw_snippet=line,
                raw_line_number=line_number,
                parsed_fields={'uptime_ms': timestamp_ms}
            )
        
        # 无法解析的行
        return None
    
    def _determine_event_type(self, message: str, level: EventLevel) -> EventType:
        """根据消息内容确定事件类型"""
        message_lower = message.lower()
        
        # FOTA相关 (优先级最高,即使是错误也要识别为FOTA)
        if any(kw in message_lower for kw in ['fota', 'update', 'upgrade', 'flash']):
            return EventType.FOTA_STAGE
        
        # 错误相关
        if level in [EventLevel.FATAL, EventLevel.ERROR]:
            return EventType.ERROR
        
        # 网络相关
        if any(kw in message_lower for kw in ['can', 'lin', 'ethernet', 'network']):
            return EventType.NETWORK
        
        # 电源相关
        if any(kw in message_lower for kw in ['power', 'voltage', 'battery', 'sleep', 'wake']):
            return EventType.SYSTEM
        
        # 系统相关
        if any(kw in message_lower for kw in ['init', 'boot', 'reset', 'shutdown']):
            return EventType.SYSTEM
        
        return EventType.LOG
    
    def _infer_level_from_message(self, message: str) -> EventLevel:
        """从消息内容推断日志级别"""
        message_lower = message.lower()
        
        if any(kw in message_lower for kw in ['fatal', 'panic', 'crash']):
            return EventLevel.FATAL
        
        if any(kw in message_lower for kw in ['error', 'fail', 'failed']):
            return EventLevel.ERROR
        
        if any(kw in message_lower for kw in ['warn', 'warning']):
            return EventLevel.WARN
        
        if any(kw in message_lower for kw in ['debug', 'trace']):
            return EventLevel.DEBUG
        
        return EventLevel.INFO
    
    def parse_stream(
        self,
        lines: Iterator[str],
        time_window: Optional[tuple] = None,
        max_lines: Optional[int] = None
    ) -> List[ParsedEvent]:
        """流式解析日志"""
        events = []
        
        for line_number, line in enumerate(lines, 1):
            if max_lines and line_number > max_lines:
                break
            
            event = self.parse_line(line, line_number)
            
            if event:
                # 时间窗口过滤
                if time_window:
                    start_time, end_time = time_window
                    if not (start_time <= event.timestamp <= end_time):
                        continue
                
                events.append(event)
        
        return events
    
    def get_source_type(self) -> str:
        """返回解析器类型"""
        return 'mcu'
    
    def validate_format(self, sample_lines: List[str]) -> bool:
        """验证日志格式"""
        if not sample_lines:
            return False
        
        # 检查前几行是否匹配MCU log格式
        matches = 0
        for line in sample_lines[:10]:
            if (self.format1_pattern.match(line) or 
                self.format2_pattern.match(line) or 
                self.format3_pattern.match(line)):
                matches += 1
        
        # 至少30%的行匹配
        return matches >= len(sample_lines[:10]) * 0.3
    
    def set_base_time(self, base_time: datetime):
        """设置基准时间（用于相对时间转换）"""
        self.base_time = base_time
