"""
DLT Log Parser

解析AUTOSAR DLT (Diagnostic Log and Trace) 格式日志
DLT是汽车行业标准的日志格式
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Iterator
from base import BaseParser, ParsedEvent, EventLevel, EventType


class DLTParser(BaseParser):
    """DLT日志解析器"""
    
    def __init__(self):
        super().__init__(
            source_type="dlt",
            parser_name="parser_dlt",
            parser_version="1.0.0"
        )
        
        # DLT文本格式示例:
        # 2024/01/01 10:00:00.123456 123456 ECU1 APP1 CTX1 log info V 1 [Message text]
        # timestamp counter ecu_id app_id ctx_id type level mode args [payload]
        
        self.dlt_pattern = re.compile(
            r'^(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{6})\s+'  # timestamp
            r'(\d+)\s+'  # counter
            r'([A-Z0-9]+)\s+'  # ECU ID
            r'([A-Z0-9]+)\s+'  # Application ID
            r'([A-Z0-9]+)\s+'  # Context ID
            r'(log|app_trace|nw_trace|control)\s+'  # message type
            r'(fatal|error|warn|info|debug|verbose)\s+'  # log level
            r'([VN])\s+'  # mode (V=verbose, N=non-verbose)
            r'(\d+)\s+'  # number of arguments
            r'\[(.+)\]$'  # payload
        )
        
        # 简化格式（某些DLT工具导出）
        self.simple_pattern = re.compile(
            r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+'  # timestamp
            r'\[([A-Z0-9]+)\]\s+'  # app_id
            r'\[([A-Z]+)\]\s+'  # level
            r'(.+)$'  # message
        )
        
        # Level mapping
        self.level_map = {
            'fatal': EventLevel.FATAL,
            'error': EventLevel.ERROR,
            'warn': EventLevel.WARN,
            'info': EventLevel.INFO,
            'debug': EventLevel.DEBUG,
            'verbose': EventLevel.DEBUG,
        }
        
        # Message type mapping
        self.type_map = {
            'log': EventType.LOG,
            'app_trace': EventType.SYSTEM,
            'nw_trace': EventType.NETWORK,
            'control': EventType.SYSTEM,
        }
    
    def parse_file(
        self,
        file_path: Path,
        time_window: Optional[tuple[datetime, datetime]] = None,
        max_lines: Optional[int] = None
    ) -> Iterator[ParsedEvent]:
        """解析DLT日志文件"""
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
        
        # 尝试完整DLT格式
        match = self.dlt_pattern.match(line)
        if match:
            timestamp_str = match.group(1)
            counter = int(match.group(2))
            ecu_id = match.group(3)
            app_id = match.group(4)
            ctx_id = match.group(5)
            msg_type = match.group(6)
            level_str = match.group(7)
            mode = match.group(8)
            num_args = int(match.group(9))
            payload = match.group(10)
            
            # 解析时间戳
            try:
                timestamp = datetime.strptime(timestamp_str, '%Y/%m/%d %H:%M:%S.%f')
            except ValueError:
                timestamp = datetime.now()
            
            # 确定日志级别
            level = self.level_map.get(level_str, EventLevel.INFO)
            
            # 确定事件类型
            event_type = self.type_map.get(msg_type, EventType.LOG)
            event_type = self._refine_event_type(payload, event_type, level)
            
            # 构建模块名
            module = f"{app_id}.{ctx_id}"
            
            # 元数据
            metadata = {
                'ecu_id': ecu_id,
                'app_id': app_id,
                'ctx_id': ctx_id,
                'counter': counter,
                'msg_type': msg_type,
                'mode': mode,
                'num_args': num_args
            }
            
            return self._create_event(
                original_ts=timestamp,                level=level,
                event_type=event_type,
                module=module,
                message=payload,
                raw_snippet=line,
                raw_line_number=line_number,
                parsed_fields=metadata
            )
        
        # 尝试简化格式
        match = self.simple_pattern.match(line)
        if match:
            timestamp_str = match.group(1)
            app_id = match.group(2)
            level_str = match.group(3).lower()
            message = match.group(4)
            
            # 解析时间戳
            try:
                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
            except ValueError:
                timestamp = datetime.now()
            
            # 确定日志级别
            level = self.level_map.get(level_str, EventLevel.INFO)
            
            # 确定事件类型
            event_type = self._refine_event_type(message, EventType.LOG, level)
            
            return self._create_event(
                original_ts=timestamp,                level=level,
                event_type=event_type,
                module=app_id,
                message=message,
                raw_snippet=line,
                raw_line_number=line_number,
                parsed_fields={'app_id': app_id}
            )
        
        # 无法解析的行
        return None
    
    def _refine_event_type(
        self, 
        message: str, 
        default_type: EventType,
        level: EventLevel
    ) -> EventType:
        """根据消息内容细化事件类型"""
        message_lower = message.lower()
        
        # 错误相关
        if level in [EventLevel.FATAL, EventLevel.ERROR]:
            if any(kw in message_lower for kw in ['crash', 'panic', 'abort']):
                return EventType.CRASH
            return EventType.ERROR
        
        # FOTA相关
        if any(kw in message_lower for kw in ['fota', 'ota', 'update', 'flash', 'upgrade']):
            return EventType.FOTA
        
        # 网络相关
        if any(kw in message_lower for kw in ['can', 'lin', 'ethernet', 'tcp', 'udp', 'socket']):
            return EventType.NETWORK
        
        # 诊断相关
        if any(kw in message_lower for kw in ['dtc', 'diagnostic', 'uds', 'obd']):
            return EventType.SYSTEM
        
        # 系统相关
        if any(kw in message_lower for kw in ['boot', 'init', 'shutdown', 'reset']):
            return EventType.SYSTEM
        
        return default_type
    
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
        return 'dlt'
    
    def validate_format(self, sample_lines: List[str]) -> bool:
        """验证日志格式"""
        if not sample_lines:
            return False
        
        # 检查前几行是否匹配DLT格式
        matches = 0
        for line in sample_lines[:10]:
            if (self.dlt_pattern.match(line) or 
                self.simple_pattern.match(line)):
                matches += 1
        
        # 至少30%的行匹配
        return matches >= len(sample_lines[:10]) * 0.3
