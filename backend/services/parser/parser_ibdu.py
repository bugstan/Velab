"""
iBDU Log Parser

解析iBDU (intelligent Battery Disconnect Unit) 日志
iBDU是智能电池断开单元，负责电源管理
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Iterator
from base import BaseParser, ParsedEvent, EventLevel, EventType


class IBDUParser(BaseParser):
    """iBDU日志解析器"""
    
    def __init__(self):
        super().__init__(
            source_type="ibdu",
            parser_name="parser_ibdu",
            parser_version="1.0.0"
        )
        
        # iBDU log格式示例:
        # 2024-01-01 10:00:00.123 [POWER] INFO: Battery voltage: 12.5V
        # timestamp [module] level: message
        
        self.ibdu_pattern = re.compile(
            r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+'  # timestamp
            r'\[([A-Z_]+)\]\s+'  # module
            r'([A-Z]+):\s*'  # level
            r'(.+)$'  # message
        )
        
        # 简化格式
        self.simple_pattern = re.compile(
            r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+'  # timestamp
            r'([A-Z]+)\s+'  # level
            r'(.+)$'  # message
        )
        
        # Level mapping
        self.level_map = {
            'FATAL': EventLevel.FATAL,
            'ERROR': EventLevel.ERROR,
            'WARN': EventLevel.WARN,
            'WARNING': EventLevel.WARN,
            'INFO': EventLevel.INFO,
            'DEBUG': EventLevel.DEBUG,
        }
        
        # 电压/电流提取
        self.voltage_pattern = re.compile(r'(\d+\.?\d*)\s*V')
        self.current_pattern = re.compile(r'(\d+\.?\d*)\s*[mM]?A')
        self.temperature_pattern = re.compile(r'(\d+\.?\d*)\s*[°]?C')
        self.percentage_pattern = re.compile(r'(\d+\.?\d*)\s*%')
    
    def parse_file(
        self,
        file_path: Path,
        time_window: Optional[tuple[datetime, datetime]] = None,
        max_lines: Optional[int] = None
    ) -> Iterator[ParsedEvent]:
        """解析iBDU日志文件"""
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
        
        # 尝试完整格式
        match = self.ibdu_pattern.match(line)
        if match:
            timestamp_str = match.group(1)
            module = match.group(2)
            level_str = match.group(3)
            message = match.group(4).strip()
            
            # 解析时间戳
            try:
                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
            except ValueError:
                try:
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    timestamp = datetime.now()
            
            # 确定日志级别
            level = self.level_map.get(level_str, EventLevel.INFO)
            
            # 确定事件类型
            event_type = self._determine_event_type(message, module, level)
            
            # 提取电气参数
            metadata = self._extract_electrical_params(message)
            
            return self._create_event(
                original_ts=timestamp,                level=level,
                event_type=event_type,
                module=module,
                message=message,
                raw_snippet=line,
                raw_line_number=line_number,
                parsed_fields=metadata
            )
        
        # 尝试简化格式
        match = self.simple_pattern.match(line)
        if match:
            timestamp_str = match.group(1)
            level_str = match.group(2)
            message = match.group(3).strip()
            
            # 解析时间戳
            try:
                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                timestamp = datetime.now()
            
            # 确定日志级别
            level = self.level_map.get(level_str, EventLevel.INFO)
            
            # 从消息推断模块
            module = self._infer_module(message)
            
            # 确定事件类型
            event_type = self._determine_event_type(message, module, level)
            
            # 提取电气参数
            metadata = self._extract_electrical_params(message)
            
            return self._create_event(
                original_ts=timestamp,                level=level,
                event_type=event_type,
                module=module,
                message=message,
                raw_snippet=line,
                raw_line_number=line_number,
                parsed_fields=metadata
            )
        
        # 无法解析的行
        return None
    
    def _determine_event_type(
        self, 
        message: str, 
        module: str,
        level: EventLevel
    ) -> EventType:
        """根据消息内容确定事件类型"""
        message_lower = message.lower()
        module_lower = module.lower()
        
        # 错误相关
        if level in [EventLevel.FATAL, EventLevel.ERROR]:
            return EventType.ERROR
        
        # 电源相关（iBDU的主要功能）
        if any(kw in message_lower or kw in module_lower 
               for kw in ['power', 'battery', 'voltage', 'current', 'charge', 'discharge']):
            return EventType.SYSTEM
        
        # FOTA相关
        if any(kw in message_lower for kw in ['fota', 'update', 'flash']):
            return EventType.FOTA_STAGE
        
        # 系统相关
        if any(kw in message_lower for kw in ['boot', 'init', 'shutdown', 'sleep', 'wake']):
            return EventType.SYSTEM
        
        # 诊断相关
        if any(kw in message_lower for kw in ['diagnostic', 'dtc', 'fault']):
            return EventType.SYSTEM
        
        return EventType.LOG
    
    def _infer_module(self, message: str) -> str:
        """从消息推断模块名"""
        message_lower = message.lower()
        
        if any(kw in message_lower for kw in ['battery', 'voltage', 'current']):
            return 'POWER'
        
        if any(kw in message_lower for kw in ['charge', 'charging']):
            return 'CHARGER'
        
        if any(kw in message_lower for kw in ['temperature', 'thermal']):
            return 'THERMAL'
        
        if any(kw in message_lower for kw in ['can', 'network']):
            return 'NETWORK'
        
        if any(kw in message_lower for kw in ['diagnostic', 'dtc']):
            return 'DIAG'
        
        return 'IBDU'
    
    def _extract_electrical_params(self, message: str) -> Dict[str, Any]:
        """提取电气参数"""
        metadata = {}
        
        # 提取电压
        voltage_match = self.voltage_pattern.search(message)
        if voltage_match:
            metadata['voltage'] = float(voltage_match.group(1))
        
        # 提取电流
        current_match = self.current_pattern.search(message)
        if current_match:
            current_value = float(current_match.group(1))
            # 如果是mA，转换为A
            if 'm' in current_match.group(0).lower():
                current_value = current_value / 1000.0
            metadata['current'] = current_value
        
        # 提取温度
        temp_match = self.temperature_pattern.search(message)
        if temp_match:
            metadata['temperature'] = float(temp_match.group(1))
        
        # 提取百分比（如电池电量）
        pct_match = self.percentage_pattern.search(message)
        if pct_match:
            metadata['percentage'] = float(pct_match.group(1))
        
        return metadata
    
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
        return 'ibdu'
    
    def validate_format(self, sample_lines: List[str]) -> bool:
        """验证日志格式"""
        if not sample_lines:
            return False
        
        # 检查前几行是否匹配iBDU格式
        matches = 0
        for line in sample_lines[:10]:
            if (self.ibdu_pattern.match(line) or 
                self.simple_pattern.match(line)):
                matches += 1
        
        # 至少30%的行匹配
        return matches >= len(sample_lines[:10]) * 0.3
