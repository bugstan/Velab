"""
Android Logcat 解析器

解析 Android logcat 格式的日志文件，支持以下格式：
- threadtime: 12-28 18:54:07.180  1234  5678 I Tag: message
- time: 12-28 18:54:07.180 I/Tag(1234): message
- brief: I/Tag(1234): message

作者：FOTA 诊断平台团队
创建时间：2026-04-03
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from base import BaseParser, ParsedEvent, EventLevel, EventType, registry


class AndroidParser(BaseParser):
    """
    Android logcat 日志解析器
    
    支持解析标准的 Android logcat 输出格式，提取时间戳、进程ID、
    线程ID、日志级别、标签和消息内容。
    """
    
    # Android logcat threadtime 格式正则表达式
    # 格式: 12-28 18:54:07.180  1234  5678 I Tag: message
    THREADTIME_PATTERN = re.compile(
        r'^(?P<month>\d{2})-(?P<day>\d{2})\s+'
        r'(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\.(?P<ms>\d{3})\s+'
        r'(?P<pid>\d+)\s+'
        r'(?P<tid>\d+)\s+'
        r'(?P<level>[VDIWEF])\s+'
        r'(?P<tag>[^:]+):\s*'
        r'(?P<message>.*)$'
    )
    
    # Android logcat time 格式正则表达式
    # 格式: 12-28 18:54:07.180 I/Tag(1234): message
    TIME_PATTERN = re.compile(
        r'^(?P<month>\d{2})-(?P<day>\d{2})\s+'
        r'(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\.(?P<ms>\d{3})\s+'
        r'(?P<level>[VDIWEF])/(?P<tag>[^(]+)\((?P<pid>\d+)\):\s*'
        r'(?P<message>.*)$'
    )
    
    # 日志级别映射
    LEVEL_MAP = {
        'V': EventLevel.DEBUG,  # Verbose
        'D': EventLevel.DEBUG,  # Debug
        'I': EventLevel.INFO,   # Info
        'W': EventLevel.WARN,   # Warning
        'E': EventLevel.ERROR,  # Error
        'F': EventLevel.FATAL,  # Fatal
    }
    
    def __init__(self):
        super().__init__(
            source_type="android",
            parser_name="parser_android",
            parser_version="1.0.0"
        )
        self.current_year = datetime.now().year  # Android logcat 不包含年份
    
    def parse_file(
        self,
        file_path: Path,
        time_window: Optional[tuple[datetime, datetime]] = None,
        max_lines: Optional[int] = None
    ) -> Iterator[ParsedEvent]:
        """
        解析 Android logcat 文件
        
        Args:
            file_path: 日志文件路径
            time_window: 可选的时间窗口
            max_lines: 可选的最大解析行数
        
        Yields:
            ParsedEvent: 解析后的事件
        """
        if not file_path.exists():
            raise FileNotFoundError(f"日志文件不存在: {file_path}")
        
        line_number = 0
        parsed_count = 0
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line_number += 1
                line = line.rstrip('\n\r')
                
                # 跳过空行
                if not line.strip():
                    continue
                
                # 尝试解析当前行
                event = self._parse_line(line, line_number)
                
                if event:
                    # 时间窗口裁剪优化
                    if self._should_skip_line(event.original_ts, time_window):
                        continue
                    
                    parsed_count += 1
                    yield event
                    
                    # 达到最大行数限制
                    if max_lines and parsed_count >= max_lines:
                        break
    
    def _parse_line(self, line: str, line_number: int) -> Optional[ParsedEvent]:
        """
        解析单行日志
        
        Args:
            line: 日志行内容
            line_number: 行号
        
        Returns:
            ParsedEvent: 解析后的事件，解析失败返回None
        """
        # 尝试 threadtime 格式
        match = self.THREADTIME_PATTERN.match(line)
        if match:
            return self._create_event_from_match(match, line, line_number, has_tid=True)
        
        # 尝试 time 格式
        match = self.TIME_PATTERN.match(line)
        if match:
            return self._create_event_from_match(match, line, line_number, has_tid=False)
        
        # 无法解析的行，可能是多行日志的续行
        # 返回None，由调用方决定如何处理
        return None
    
    def _create_event_from_match(
        self,
        match: re.Match,
        line: str,
        line_number: int,
        has_tid: bool
    ) -> ParsedEvent:
        """
        从正则匹配结果创建事件对象
        
        Args:
            match: 正则匹配对象
            line: 原始日志行
            line_number: 行号
            has_tid: 是否包含线程ID
        
        Returns:
            ParsedEvent: 标准化事件对象
        """
        groups = match.groupdict()
        
        # 构造时间戳（Android logcat 不包含年份，使用当前年份）
        timestamp = datetime(
            year=self.current_year,
            month=int(groups['month']),
            day=int(groups['day']),
            hour=int(groups['hour']),
            minute=int(groups['minute']),
            second=int(groups['second']),
            microsecond=int(groups['ms']) * 1000
        )
        
        # 映射日志级别
        level_char = groups['level']
        level = self.LEVEL_MAP.get(level_char, EventLevel.INFO)
        
        # 确定事件类型
        event_type = EventType.ERROR if level in (EventLevel.ERROR, EventLevel.FATAL) else EventType.LOG
        
        # 提取模块名（从tag中推断）
        tag = groups['tag'].strip()
        module = self._extract_module_from_tag(tag)
        
        # 构造结构化字段
        parsed_fields = {
            'pid': int(groups['pid']),
            'tag': tag,
        }
        
        if has_tid:
            parsed_fields['tid'] = int(groups['tid'])
        
        return self._create_event(
            message=groups['message'],
            raw_line_number=line_number,
            original_ts=timestamp,
            event_type=event_type,
            level=level,
            module=module,
            process=groups['pid'],
            thread=groups.get('tid'),
            tag=tag,
            raw_snippet=line,
            parsed_fields=parsed_fields
        )
    
    def _extract_module_from_tag(self, tag: str) -> Optional[str]:
        """
        从 Android tag 中提取模块名
        
        常见模式：
        - FotaDownloadImpl -> FotaDownloadImpl
        - com.maxus.fota.FotaService -> FotaService
        
        Args:
            tag: Android logcat tag
        
        Returns:
            str: 模块名，如果无法提取则返回tag本身
        """
        # 如果tag包含包名，提取最后一部分
        if '.' in tag:
            return tag.split('.')[-1]
        return tag


# 注册解析器到全局注册表
registry.register("android", AndroidParser)
