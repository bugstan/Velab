"""
Parser Service - 多格式日志解析服务

本模块提供可插拔的日志解析器架构，支持7种日志格式：
- Android logcat
- Kernel / tombstone / ANR
- FOTA 文本日志
- DLT 格式
- MCU 日志
- iBDU 日志
- 车型信号导出文件

作者：FOTA 诊断平台团队
创建时间：2026-04-03
"""

from .base import BaseParser, ParsedEvent, ParserRegistry
from .parser_android import AndroidParser
from .parser_fota import FotaParser
from .parser_kernel import KernelParser
from .parser_mcu import MCUParser
from .parser_dlt import DLTParser
from .parser_ibdu import IBDUParser
from .parser_vehicle_signal import VehicleSignalParser

__all__ = [
    "BaseParser",
    "ParsedEvent",
    "ParserRegistry",
    "AndroidParser",
    "FotaParser",
    "KernelParser",
    "MCUParser",
    "DLTParser",
    "IBDUParser",
    "VehicleSignalParser",
]
