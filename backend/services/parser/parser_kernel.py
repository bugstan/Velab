"""
Kernel Log Parser

解析Linux kernel日志、tombstone和ANR日志
支持格式：
- kernel log (dmesg)
- tombstone (native crash)
- ANR (Application Not Responding)
"""

import re
from datetime import datetime
from typing import Optional, Dict, Any, List, Iterator
from base import BaseParser, ParsedEvent, EventLevel, EventType


class KernelParser(BaseParser):
    """Kernel日志解析器"""
    
    def __init__(self):
        super().__init__()
        
        # Kernel log格式: [timestamp] level message
        # 例如: [  123.456789] <6>[ T1234] message
        self.kernel_pattern = re.compile(
            r'^\[\s*(\d+\.\d+)\]\s*'  # timestamp
            r'(?:<(\d+)>)?'  # optional level
            r'(?:\[\s*T(\d+)\])?'  # optional thread
            r'\s*(.+)$'  # message
        )
        
        # Tombstone header
        self.tombstone_pattern = re.compile(
            r'^\*\*\* \*\*\* \*\*\* \*\*\* \*\*\* \*\*\* \*\*\* \*\*\* \*\*\* \*\*\* \*\*\* \*\*\*'
        )
        
        # ANR header
        self.anr_pattern = re.compile(
            r'^----- pid (\d+) at (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) -----'
        )
        
        # Crash signal
        self.signal_pattern = re.compile(
            r'signal (\d+) \(([A-Z]+)\)'
        )
        
        # Backtrace
        self.backtrace_pattern = re.compile(
            r'#(\d+)\s+pc\s+([0-9a-f]+)\s+(.+)'
        )
        
        # Kernel panic
        self.panic_pattern = re.compile(
            r'Kernel panic|BUG:|Oops:|Call Trace:',
            re.IGNORECASE
        )
        
        # Level mapping (kernel log levels)
        self.level_map = {
            '0': EventLevel.FATAL,    # KERN_EMERG
            '1': EventLevel.FATAL,    # KERN_ALERT
            '2': EventLevel.CRITICAL, # KERN_CRIT
            '3': EventLevel.ERROR,    # KERN_ERR
            '4': EventLevel.WARN,     # KERN_WARNING
            '5': EventLevel.INFO,     # KERN_NOTICE
            '6': EventLevel.INFO,     # KERN_INFO
            '7': EventLevel.DEBUG,    # KERN_DEBUG
        }
    
    def parse_line(
        self,
        line: str,
        line_number: int,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[ParsedEvent]:
        """解析单行日志"""
        if not line.strip():
            return None
        
        # 初始化上下文
        if context is None:
            context = {
                'in_tombstone': False,
                'in_anr': False,
                'in_backtrace': False,
                'crash_info': {},
                'backtrace_lines': []
            }
        
        # 检查是否是tombstone开始
        if self.tombstone_pattern.match(line):
            context['in_tombstone'] = True
            context['crash_info'] = {}
            context['backtrace_lines'] = []
            return None
        
        # 检查是否是ANR开始
        anr_match = self.anr_pattern.match(line)
        if anr_match:
            context['in_anr'] = True
            pid = anr_match.group(1)
            timestamp_str = anr_match.group(2)
            
            try:
                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                timestamp = datetime.now()
            
            return ParsedEvent(
                timestamp=timestamp,
                source_type='kernel',
                level=EventLevel.ERROR,
                event_type=EventType.ANR,
                module='ANR',
                message=f'ANR detected in process {pid}',
                raw=line,
                line_number=line_number,
                metadata={'pid': pid}
            )
        
        # 解析kernel log格式
        kernel_match = self.kernel_pattern.match(line)
        if kernel_match:
            timestamp_sec = float(kernel_match.group(1))
            level_str = kernel_match.group(2) or '6'
            tid = kernel_match.group(3)
            message = kernel_match.group(4).strip()
            
            # 转换时间戳（从系统启动时间）
            timestamp = datetime.fromtimestamp(timestamp_sec)
            
            # 确定日志级别
            level = self.level_map.get(level_str, EventLevel.INFO)
            
            # 检查是否是panic
            if self.panic_pattern.search(message):
                level = EventLevel.FATAL
                event_type = EventType.CRASH
            else:
                event_type = EventType.SYSTEM
            
            # 提取模块名
            module = self._extract_module(message)
            
            # 检查信号
            signal_match = self.signal_pattern.search(message)
            metadata = {}
            if signal_match:
                metadata['signal'] = signal_match.group(1)
                metadata['signal_name'] = signal_match.group(2)
                event_type = EventType.CRASH
            
            if tid:
                metadata['tid'] = tid
            
            # 检查backtrace
            backtrace_match = self.backtrace_pattern.match(message)
            if backtrace_match:
                context['in_backtrace'] = True
                context['backtrace_lines'].append(line)
                return None  # 累积backtrace，稍后一起返回
            
            # 如果之前在累积backtrace，现在结束了
            if context.get('in_backtrace') and not backtrace_match:
                context['in_backtrace'] = False
                if context['backtrace_lines']:
                    metadata['stack_trace'] = '\n'.join(context['backtrace_lines'])
                    context['backtrace_lines'] = []
            
            return ParsedEvent(
                timestamp=timestamp,
                source_type='kernel',
                level=level,
                event_type=event_type,
                module=module,
                message=message,
                raw=line,
                line_number=line_number,
                metadata=metadata
            )
        
        # 如果在tombstone或ANR中，继续收集信息
        if context.get('in_tombstone') or context.get('in_anr'):
            # 检查backtrace
            if self.backtrace_pattern.match(line):
                context['backtrace_lines'].append(line)
            return None
        
        # 无法解析的行
        return None
    
    def _extract_module(self, message: str) -> str:
        """从消息中提取模块名"""
        # 常见模式: [module] message 或 module: message
        patterns = [
            r'^\[([^\]]+)\]',
            r'^([a-zA-Z0-9_-]+):',
            r'^([a-zA-Z0-9_-]+)\s+',
        ]
        
        for pattern in patterns:
            match = re.match(pattern, message)
            if match:
                return match.group(1)
        
        # 检查常见的kernel子系统
        subsystems = [
            'mm', 'fs', 'net', 'block', 'usb', 'pci', 'cpu', 
            'sched', 'irq', 'timer', 'workqueue', 'rcu'
        ]
        
        message_lower = message.lower()
        for subsystem in subsystems:
            if subsystem in message_lower:
                return subsystem
        
        return 'kernel'
    
    def parse_stream(
        self,
        lines: Iterator[str],
        time_window: Optional[tuple] = None,
        max_lines: Optional[int] = None
    ) -> List[ParsedEvent]:
        """流式解析日志"""
        events = []
        context = {
            'in_tombstone': False,
            'in_anr': False,
            'in_backtrace': False,
            'crash_info': {},
            'backtrace_lines': []
        }
        
        for line_number, line in enumerate(lines, 1):
            if max_lines and line_number > max_lines:
                break
            
            event = self.parse_line(line, line_number, context)
            
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
        return 'kernel'
    
    def validate_format(self, sample_lines: List[str]) -> bool:
        """验证日志格式"""
        if not sample_lines:
            return False
        
        # 检查前几行是否匹配kernel log格式
        matches = 0
        for line in sample_lines[:10]:
            if self.kernel_pattern.match(line):
                matches += 1
            elif self.tombstone_pattern.match(line):
                matches += 1
            elif self.anr_pattern.match(line):
                matches += 1
        
        # 至少30%的行匹配
        return matches >= len(sample_lines[:10]) * 0.3
