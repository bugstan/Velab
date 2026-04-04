"""
Vehicle Signal Parser

解析车辆信号导出文件
通常是CSV或类似格式，包含车速、转速、档位等信号
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Iterator
from base import BaseParser, ParsedEvent, EventLevel, EventType


class VehicleSignalParser(BaseParser):
    """车辆信号解析器"""
    
    def __init__(self):
        super().__init__(
            source_type="vehicle_signal",
            parser_name="parser_vehicle_signal",
            parser_version="1.0.0"
        )
        
        # CSV格式: timestamp,signal_name,value,unit
        # 例如: 2024-01-01 10:00:00.123,VehicleSpeed,60.5,km/h
        
        self.csv_pattern = re.compile(
            r'^([^,]+),\s*'  # timestamp
            r'([^,]+),\s*'  # signal name
            r'([^,]+),?\s*'  # value
            r'(.*)$'  # optional unit
        )
        
        # 表格格式: timestamp | signal | value | unit
        self.table_pattern = re.compile(
            r'^([^\|]+)\|\s*'  # timestamp
            r'([^\|]+)\|\s*'  # signal name
            r'([^\|]+)\|?\s*'  # value
            r'(.*)$'  # optional unit
        )
        
        # 关键信号列表
        self.critical_signals = {
            'VehicleSpeed', 'EngineSpeed', 'GearPosition', 
            'BatteryVoltage', 'EngineTemperature', 'FuelLevel',
            'BrakeStatus', 'AcceleratorPosition', 'SteeringAngle'
        }
        
        # 信号类别映射
        self.signal_categories = {
            'speed': ['VehicleSpeed', 'EngineSpeed', 'WheelSpeed'],
            'power': ['BatteryVoltage', 'BatteryCurrent', 'PowerConsumption'],
            'engine': ['EngineSpeed', 'EngineTemperature', 'EngineLoad'],
            'transmission': ['GearPosition', 'TransmissionTemperature'],
            'brake': ['BrakeStatus', 'BrakePressure', 'ABSStatus'],
            'steering': ['SteeringAngle', 'SteeringTorque'],
        }
    
    def parse_file(
        self,
        file_path: Path,
        time_window: Optional[tuple[datetime, datetime]] = None,
        max_lines: Optional[int] = None
    ) -> Iterator[ParsedEvent]:
        """解析车辆信号文件"""
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
        
        # 跳过表头
        if line_number == 1 and any(kw in line.lower() 
                                     for kw in ['timestamp', 'signal', 'value']):
            return None
        
        # 尝试CSV格式
        match = self.csv_pattern.match(line)
        if not match:
            # 尝试表格格式
            match = self.table_pattern.match(line)
        
        if match:
            timestamp_str = match.group(1).strip()
            signal_name = match.group(2).strip()
            value_str = match.group(3).strip()
            unit = match.group(4).strip() if len(match.groups()) >= 4 else ''
            
            # 解析时间戳
            timestamp = self._parse_timestamp(timestamp_str)
            if not timestamp:
                return None
            
            # 解析值
            try:
                value = float(value_str)
            except ValueError:
                # 如果不是数字，可能是状态值
                value = value_str
            
            # 确定信号类别
            category = self._get_signal_category(signal_name)
            
            # 确定事件类型
            event_type = self._determine_event_type(signal_name, value, category)
            
            # 确定日志级别
            level = self._determine_level(signal_name, value)
            
            # 构建消息
            if isinstance(value, float):
                message = f"{signal_name}: {value:.2f} {unit}".strip()
            else:
                message = f"{signal_name}: {value} {unit}".strip()
            
            # 元数据
            metadata = {
                'signal_name': signal_name,
                'value': value,
                'unit': unit,
                'category': category,
                'is_critical': signal_name in self.critical_signals
            }
            
            return self._create_event(
                original_ts=timestamp,                level=level,
                event_type=event_type,
                module=category,
                message=message,
                raw_snippet=line,
                raw_line_number=line_number,
                parsed_fields=metadata
            )
        
        # 无法解析的行
        return None
    
    def _parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """解析时间戳（支持多种格式）"""
        formats = [
            '%Y-%m-%d %H:%M:%S.%f',
            '%Y-%m-%d %H:%M:%S',
            '%Y/%m/%d %H:%M:%S.%f',
            '%Y/%m/%d %H:%M:%S',
            '%d-%m-%Y %H:%M:%S',
            '%d/%m/%Y %H:%M:%S',
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(timestamp_str, fmt)
            except ValueError:
                continue
        
        return None
    
    def _get_signal_category(self, signal_name: str) -> str:
        """获取信号类别"""
        signal_lower = signal_name.lower()
        
        for category, signals in self.signal_categories.items():
            for sig in signals:
                if sig.lower() in signal_lower:
                    return category
        
        return 'general'
    
    def _determine_event_type(
        self, 
        signal_name: str, 
        value: Any,
        category: str
    ) -> EventType:
        """根据信号确定事件类型"""
        # 电源相关
        if category == 'power':
            return EventType.SYSTEM
        
        # 诊断相关
        if 'dtc' in signal_name.lower() or 'fault' in signal_name.lower():
            return EventType.SYSTEM
        
        # 系统相关
        if 'ignition' in signal_name.lower() or 'key' in signal_name.lower():
            return EventType.SYSTEM
        
        return EventType.LOG
    
    def _determine_level(self, signal_name: str, value: Any) -> EventLevel:
        """根据信号值确定日志级别"""
        signal_lower = signal_name.lower()
        
        # 电池电压异常
        if 'voltage' in signal_lower and isinstance(value, (int, float)):
            if value < 11.0 or value > 15.0:
                return EventLevel.WARN
        
        # 温度异常
        if 'temperature' in signal_lower and isinstance(value, (int, float)):
            if value > 100:
                return EventLevel.ERROR
            elif value > 90:
                return EventLevel.WARN
        
        # 速度异常
        if 'speed' in signal_lower and isinstance(value, (int, float)):
            if value > 200:
                return EventLevel.WARN
        
        # 故障码
        if 'dtc' in signal_lower or 'fault' in signal_lower:
            if value and value != '0' and value != 0:
                return EventLevel.ERROR
        
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
        return 'vehicle_signal'
    
    def validate_format(self, sample_lines: List[str]) -> bool:
        """验证日志格式"""
        if not sample_lines:
            return False
        
        # 检查是否有表头
        header_keywords = ['timestamp', 'signal', 'value', 'time', 'name']
        has_header = any(kw in sample_lines[0].lower() for kw in header_keywords)
        
        # 检查数据行
        start_line = 1 if has_header else 0
        matches = 0
        
        for line in sample_lines[start_line:min(start_line + 10, len(sample_lines))]:
            if (self.csv_pattern.match(line) or 
                self.table_pattern.match(line)):
                matches += 1
        
        # 至少30%的行匹配
        total_lines = min(10, len(sample_lines) - start_line)
        return matches >= total_lines * 0.3 if total_lines > 0 else False
