"""
FOTA 文本日志解析器

解析 FOTA 系统的文本日志文件，识别 FOTA 升级的各个阶段和关键事件。

典型日志格式示例：
2024-12-28 18:54:07.180 [INFO] [FotaDownloadImpl] Download started: version=1.2.3
2024-12-28 18:54:08.250 [ERROR] [FotaVerifyImpl] Signature verification failed

作者：FOTA 诊断平台团队
创建时间：2026-04-03
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from base import BaseParser, ParsedEvent, EventLevel, EventType, registry


class FotaParser(BaseParser):
    """
    FOTA 文本日志解析器
    
    解析 FOTA 系统的文本日志，识别升级阶段转换、错误事件和关键状态变更。
    """
    
    # FOTA 日志格式正则表达式
    # 格式: 2024-12-28 18:54:07.180 [INFO] [FotaDownloadImpl] message
    LOG_PATTERN = re.compile(
        r'^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})\s+'
        r'(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\.(?P<ms>\d{3})\s+'
        r'\[(?P<level>[A-Z]+)\]\s+'
        r'\[(?P<module>[^\]]+)\]\s+'
        r'(?P<message>.*)$'
    )
    
    # 日志级别映射
    LEVEL_MAP = {
        'TRACE': EventLevel.DEBUG,
        'DEBUG': EventLevel.DEBUG,
        'INFO': EventLevel.INFO,
        'WARN': EventLevel.WARN,
        'WARNING': EventLevel.WARN,
        'ERROR': EventLevel.ERROR,
        'FATAL': EventLevel.FATAL,
    }
    
    # FOTA 阶段关键词识别
    FOTA_STAGE_KEYWORDS = {
        'init': ['initialization', 'init', 'startup', 'starting'],
        'check': ['version check', 'checking version', 'query version'],
        'download': ['download start', 'downloading', 'download progress'],
        'verify': ['verification', 'verify', 'signature check', 'checksum'],
        'install': ['installation', 'installing', 'flashing', 'writing'],
        'reboot': ['reboot', 'restart', 'rebooting'],
        'complete': ['upgrade complete', 'success', 'finished'],
        'failed': ['failed', 'failure', 'error', 'abort'],
    }
    
    def __init__(self):
        super().__init__(
            source_type="fota",
            parser_name="parser_fota",
            parser_version="1.0.0"
        )
    
    def parse_file(
        self,
        file_path: Path,
        time_window: Optional[tuple[datetime, datetime]] = None,
        max_lines: Optional[int] = None
    ) -> Iterator[ParsedEvent]:
        """
        解析 FOTA 日志文件
        
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
        match = self.LOG_PATTERN.match(line)
        if not match:
            return None
        
        groups = match.groupdict()
        
        # 构造时间戳
        timestamp = datetime(
            year=int(groups['year']),
            month=int(groups['month']),
            day=int(groups['day']),
            hour=int(groups['hour']),
            minute=int(groups['minute']),
            second=int(groups['second']),
            microsecond=int(groups['ms']) * 1000
        )
        
        # 映射日志级别
        level_str = groups['level'].upper()
        level = self.LEVEL_MAP.get(level_str, EventLevel.INFO)
        
        # 提取模块和消息
        module = groups['module']
        message = groups['message']
        
        # 识别事件类型和 FOTA 阶段
        event_type, fota_stage = self._identify_event_type(message, level)
        
        # 构造结构化字段
        parsed_fields = {
            'raw_level': level_str,
        }
        
        if fota_stage:
            parsed_fields['fota_stage'] = fota_stage
        
        # 提取关键信息（版本号、文件名、错误码等）
        extracted_info = self._extract_key_info(message)
        if extracted_info:
            parsed_fields.update(extracted_info)
        
        return self._create_event(
            message=message,
            raw_line_number=line_number,
            original_ts=timestamp,
            event_type=event_type,
            level=level,
            module=module,
            raw_snippet=line,
            parsed_fields=parsed_fields
        )
    
    def _identify_event_type(self, message: str, level: EventLevel) -> tuple[EventType, Optional[str]]:
        """
        识别事件类型和 FOTA 阶段
        
        Args:
            message: 日志消息
            level: 日志级别
        
        Returns:
            tuple: (事件类型, FOTA阶段)
        """
        message_lower = message.lower()
        
        # 识别 FOTA 阶段
        fota_stage = None
        for stage, keywords in self.FOTA_STAGE_KEYWORDS.items():
            if any(keyword in message_lower for keyword in keywords):
                fota_stage = stage
                break
        
        # 确定事件类型
        if fota_stage:
            event_type = EventType.FOTA_STAGE
        elif level in (EventLevel.ERROR, EventLevel.FATAL):
            event_type = EventType.ERROR
        elif level == EventLevel.WARN:
            event_type = EventType.WARNING
        elif 'state' in message_lower or 'status' in message_lower:
            event_type = EventType.STATE_CHANGE
        else:
            event_type = EventType.LOG
        
        return event_type, fota_stage
    
    def _extract_key_info(self, message: str) -> dict:
        """
        从消息中提取关键信息
        
        提取内容包括：
        - 版本号
        - 文件名
        - 错误码
        - 进度百分比
        
        Args:
            message: 日志消息
        
        Returns:
            dict: 提取的关键信息
        """
        info = {}
        
        # 提取版本号 (version=1.2.3 或 v1.2.3)
        version_match = re.search(r'version[=:\s]+([0-9.]+)', message, re.IGNORECASE)
        if version_match:
            info['version'] = version_match.group(1)
        
        # 提取文件名
        file_match = re.search(r'file[=:\s]+([^\s,]+)', message, re.IGNORECASE)
        if file_match:
            info['filename'] = file_match.group(1)
        
        # 提取错误码 (error code: 0x1234 或 errno=123)
        error_code_match = re.search(r'(?:error\s*code|errno)[=:\s]+(?:0x)?([0-9a-fA-F]+)', message, re.IGNORECASE)
        if error_code_match:
            info['error_code'] = error_code_match.group(1)
        
        # 提取进度百分比 (progress: 45% 或 45%)
        progress_match = re.search(r'(?:progress[=:\s]+)?(\d+)%', message, re.IGNORECASE)
        if progress_match:
            info['progress'] = int(progress_match.group(1))
        
        # 提取文件大小 (size: 1024KB 或 1.5MB)
        size_match = re.search(r'size[=:\s]+([0-9.]+)\s*(KB|MB|GB)', message, re.IGNORECASE)
        if size_match:
            info['file_size'] = f"{size_match.group(1)}{size_match.group(2)}"
        
        return info


# 注册解析器到全局注册表
registry.register("fota", FotaParser)
