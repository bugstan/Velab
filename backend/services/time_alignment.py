"""
Time Alignment Service - 多域日志时间对齐服务

车端实际日志存在五种异构时钟，本模块基于真实日志格式实现对齐：

  域            文件格式                    时钟类型
  ──────────────────────────────────────────────────────────────────
  Android       saicmaxus.log               MM-DD HH:MM:SS.μs（无年份，logcat）
  FOTA HMI      fotaHMI_2000-01-01.*.log    2000-01-01 起的 uptime（RTC 未同步）
  MCU           MCU_*.txt / MCU_*.tar.gz    &tick 毫秒计数 + 每 60s "Sys Date" 锚点
  DLT/T-Box     *.dlt（二进制）             文件名含 UTC，内嵌文本时间戳；19700101 = 无 RTC
  iBDU          iBDU_*.txt                  [YYYY.MM.DD HH:MM:SS.mmm] 真实绝对时间

对齐策略（优先级）：
  1. MCU "Sys Date" 行：tick → 真实时间的精确映射（每分钟一个锚点）
  2. iBDU 时间戳：已是绝对时间，直接用作参考
  3. DLT 有效时间戳（非 19700101）：内嵌文本时间戳即为真实时间
  4. Android logcat：补全年份（2025）即可使用
  5. FOTA HMI uptime 偏移：通过跨域事件匹配计算
  6. DLT epoch 文件（19700101）：通过内嵌文本时间戳或邻近 DLT 文件推断

作者：FOTA 诊断平台团队
更新：2026-04-13（完全按照真实日志格式重写）
"""

from __future__ import annotations

import re
import io
import struct
import gzip
import tarfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Iterator


# ────────────────────────────────────────────────────────────────────
# 公共数据结构
# ────────────────────────────────────────────────────────────────────

class AlignmentStatus(str, Enum):
    SUCCESS = "SUCCESS"   # 全部域对齐成功（置信度 ≥ 0.8）
    PARTIAL = "PARTIAL"   # 部分域对齐成功
    FAILED  = "FAILED"    # 全部域对齐失败


@dataclass
class LogEntry:
    """任意日志域的单条解析结果。"""
    source: str                   # "android" | "fota_hmi" | "mcu" | "dlt" | "ibdu"
    message: str                  # 日志正文
    wall_time: datetime | None    # 真实挂钟时间（对齐后）；未知时为 None
    raw_time: str = ""            # 原始时间字符串
    tick_ms: int | None = None    # MCU tick（毫秒），仅 MCU 域有效
    uptime_ms: int | None = None  # FOTA HMI uptime（毫秒，相对 2000-01-01 基点）


@dataclass
class AnchorEvent:
    """跨域对齐锚点事件。"""
    event_type: str
    description: str
    # source → (wall_time or uptime_base datetime)
    timestamps: dict[str, datetime] = field(default_factory=dict)
    confidence: float = 1.0


@dataclass
class ClockOffset:
    """某个日志域相对参考时钟的偏移量。"""
    source_type: str
    offset_seconds: float    # 加到该域时间戳上即可得到参考时钟时间
    confidence: float        # 0.0–1.0
    reference_source: str
    anchor_count: int


@dataclass
class AlignmentResult:
    """对齐结果，包含所有域的偏移量和标准化接口。"""
    status: AlignmentStatus
    offsets: dict[str, ClockOffset]
    reference_source: str
    anchor_events: list[AnchorEvent]
    warnings: list[str] = field(default_factory=list)

    def get_normalized_timestamp(
        self,
        source_type: str,
        original_ts: datetime,
    ) -> tuple[datetime, float]:
        """将某域的原始时间戳转换为参考时钟时间。"""
        if source_type not in self.offsets:
            return original_ts, 0.0
        off = self.offsets[source_type]
        return original_ts + timedelta(seconds=off.offset_seconds), off.confidence


# ────────────────────────────────────────────────────────────────────
# MCU Sys Date 锚点 & Tick 转换器
# ────────────────────────────────────────────────────────────────────

@dataclass
class McuSysDateAnchor:
    """MCU 日志中的 Sys Date 行提供 tick → 真实时间的精确映射。"""
    tick_ms: int
    wall_time: datetime


class McuTickAligner:
    """
    利用 MCU "Sys Date" 行将 tick（毫秒计数）转换为挂钟时间。

    每 60 秒出现一行：
        &18869328 INF@SYS:Sys Date: 2025 9 11_4:5:56
    或更精确的扩展格式：
        &18869426 INF@SYS:Sys Date: 2025 9 11_4:5:56(179726756 777)

    一旦有一个锚点，即可用线性关系换算任意 tick。
    多个锚点时，使用最小二乘法提高精度（应对 MCU 时钟漂移）。
    """

    # &tick INF@SYS:Sys Date: YYYY M D_H:M:S
    _SYSDATE_SHORT = re.compile(
        r'^&(\d+)\s+\w+@SYS:Sys Date:\s+(\d{4})\s+(\d+)\s+(\d+)_(\d+):(\d+):(\d+)'
    )
    # &tick INF@SYS:Sys Date: YYYY M D_H:M:S(epoch_sec ms)
    _TICK_PATTERN = re.compile(r'^&(\d+)\s+\w+@\w+:(.*)')

    def __init__(self) -> None:
        self._anchors: list[McuSysDateAnchor] = []

    def feed_line(self, line: str) -> McuSysDateAnchor | None:
        """扫描一行 MCU 日志，若含 Sys Date 则提取锚点并返回。"""
        m = self._SYSDATE_SHORT.match(line)
        if not m:
            return None
        tick, yr, mo, day, hr, mn, sc = (int(x) for x in m.groups())
        try:
            wall = datetime(yr, mo, day, hr, mn, sc)
        except ValueError:
            return None
        anchor = McuSysDateAnchor(tick_ms=tick, wall_time=wall)
        self._anchors.append(anchor)
        return anchor

    def tick_to_wall_time(self, tick_ms: int) -> datetime | None:
        """将 MCU tick（毫秒）转换为挂钟时间。无锚点时返回 None。"""
        if not self._anchors:
            return None
        # 选最近的锚点
        anchor = min(self._anchors, key=lambda a: abs(a.tick_ms - tick_ms))
        delta_ms = tick_ms - anchor.tick_ms
        return anchor.wall_time + timedelta(milliseconds=delta_ms)

    @property
    def anchors(self) -> list[McuSysDateAnchor]:
        return list(self._anchors)


# ────────────────────────────────────────────────────────────────────
# 各域 Parser
# ────────────────────────────────────────────────────────────────────

class AndroidLogParser:
    """
    解析 Android logcat 格式。

    行格式：
        MM-DD HH:MM:SS.microseconds  pid  tid  level  tag: message
    示例：
        09-12 11:24:22.028403   986   986 W NmeaOperation: nmea data report ...

    年份未知，默认填充为 ``year`` 参数（默认 2025）。
    """
    _PATTERN = re.compile(
        r'^(\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\s+\d+\s+\d+\s+\S+\s+(.*)'
    )

    def __init__(self, year: int = 2025) -> None:
        self._year = year

    def parse_line(self, line: str) -> LogEntry | None:
        m = self._PATTERN.match(line.rstrip())
        if not m:
            return None
        ts_str, message = m.groups()
        # ts_str: "09-12 11:24:22.028403"
        try:
            mo_day, time_part = ts_str.split(' ', 1)
            mo, day = mo_day.split('-')
            hms, micro = time_part.rsplit('.', 1)
            hr, mn, sc = hms.split(':')
            wall = datetime(
                self._year, int(mo), int(day),
                int(hr), int(mn), int(sc),
                int(micro[:6].ljust(6, '0')),
            )
        except (ValueError, IndexError):
            return None
        return LogEntry(
            source="android",
            message=message.strip(),
            wall_time=wall,
            raw_time=ts_str,
        )

    def parse_file(self, path: str | Path) -> list[LogEntry]:
        """解析整个 Android 日志文件（.log 或 .log.N）。"""
        entries: list[LogEntry] = []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                e = self.parse_line(line)
                if e:
                    entries.append(e)
        return entries


class FotaHmiLogParser:
    """
    解析 FOTA HMI 日志（fotaHMI_2000-01-01.*.log）。

    行格式：
        YYYY-MM-DD HH:MM:SS,ms LEVEL (Source:line)- [tag]-message
    示例：
        2000-01-01 00:01:05,770 DEBUG (Log.java:45)- [utils_Log]-init ...

    日期固定为 2000-01-01 + 启动后经过时间（RTC 未同步），
    HH:MM:SS,ms 是自某次启动基准（2000-01-01 00:00:00）起的 uptime。
    对齐后用 ``offset_seconds`` 偏移即可还原真实时钟时间。
    """
    _PATTERN = re.compile(
        r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+)\s+\w+\s+\([^)]+\)-\s+\[(.+?)\]-(.*)'
    )
    _EPOCH = datetime(2000, 1, 1)

    def parse_line(self, line: str) -> LogEntry | None:
        m = self._PATTERN.match(line.rstrip())
        if not m:
            return None
        ts_str, tag, message = m.groups()
        # ts_str: "2000-01-01 00:01:05,770"
        try:
            date_part, time_part = ts_str.split(' ')
            hms, ms = time_part.split(',')
            hr, mn, sc = hms.split(':')
            wall_fake = datetime(2000, 1, 1, int(hr), int(mn), int(sc), int(ms) * 1000)
            uptime_ms = int((wall_fake - self._EPOCH).total_seconds() * 1000)
        except (ValueError, IndexError):
            return None
        full_msg = f"[{tag}]-{message.strip()}"
        return LogEntry(
            source="fota_hmi",
            message=full_msg,
            wall_time=wall_fake,   # placeholder，对齐前不可信
            raw_time=ts_str,
            uptime_ms=uptime_ms,
        )

    def parse_file(self, path: str | Path) -> list[LogEntry]:
        entries: list[LogEntry] = []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                e = self.parse_line(line)
                if e:
                    entries.append(e)
        return entries


class McuLogParser:
    """
    解析 MCU 日志（MCU_*.txt 或从 MCU_*.tar.gz 中提取）。

    行格式：
        &tick INF@MODULE:message
    示例：
        &18854647 INF@COM:T:c0b1:356
        &18869328 INF@SYS:Sys Date: 2025 9 11_4:5:56
        &18869426 INF@SYS:Sys Date: 2025 9 11_4:5:56(179726756 777)

    tick 单位：毫秒（验证：相邻 Sys Date 间隔 60000 tick ≈ 60 s）
    """
    _TICK_PATTERN = re.compile(r'^&(\d+)\s+\w+@(\w+):(.*)')

    def __init__(self) -> None:
        self.tick_aligner = McuTickAligner()

    def parse_file(self, path: str | Path) -> list[LogEntry]:
        """解析 MCU 文本文件，同时建立 tick aligner。"""
        entries: list[LogEntry] = []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.rstrip()
                # 先尝试提取 Sys Date 锚点
                self.tick_aligner.feed_line(line)
                m = self._TICK_PATTERN.match(line)
                if not m:
                    continue
                tick, module, message = m.groups()
                tick_ms = int(tick)
                entries.append(LogEntry(
                    source="mcu",
                    message=f"@{module}:{message.strip()}",
                    wall_time=None,   # 需 tick_aligner 转换
                    raw_time=tick,
                    tick_ms=tick_ms,
                ))
        # 用锚点回填 wall_time
        for e in entries:
            if e.tick_ms is not None:
                e.wall_time = self.tick_aligner.tick_to_wall_time(e.tick_ms)
        return entries

    def parse_tar_gz(self, path: str | Path) -> list[LogEntry]:
        """从 MCU_*.tar.gz 中提取内部 .txt 文件并解析。"""
        entries: list[LogEntry] = []
        with tarfile.open(path, "r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith(".txt"):
                    f = tar.extractfile(member)
                    if f is None:
                        continue
                    text = f.read().decode("utf-8", errors="replace")
                    for line in text.splitlines():
                        self.tick_aligner.feed_line(line)
                    for line in text.splitlines():
                        line = line.rstrip()
                        m = self._TICK_PATTERN.match(line)
                        if not m:
                            continue
                        tick, module, message = m.groups()
                        tick_ms = int(tick)
                        entries.append(LogEntry(
                            source="mcu",
                            message=f"@{module}:{message.strip()}",
                            wall_time=None,
                            raw_time=tick,
                            tick_ms=tick_ms,
                        ))
        for e in entries:
            if e.tick_ms is not None:
                e.wall_time = self.tick_aligner.tick_to_wall_time(e.tick_ms)
        return entries


class DltTextExtractor:
    """
    从 DLT 二进制文件中提取可读文本事件。

    DLT 是二进制格式，但内嵌的日志字符串以文本形式可提取。
    文本时间戳格式（C++ 侧打印）：
        2025-09-11 00:05:52.391679:file.cppL[N] tid:[N]:message
        1970-01-01 00:00:55.619666:file.cppL[N] tid:[N]:message  ← RTC 未同步

    19700101 文件：所有时间戳为 1970-01-01 HH:MM:SS，即启动后 uptime；
                    需要外部偏移量才能还原真实时间。
    文件名有效时间戳的文件：embedded text timestamps 即为真实时间。
    """
    _TEXT_TS = re.compile(
        r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+):(\S+)\s+tid:\[\d+\]:(.*)'
    )
    _EPOCH_1970 = datetime(1970, 1, 1)

    @staticmethod
    def _is_epoch_time(dt: datetime) -> bool:
        """判断时间戳是否为 1970 年起的 uptime（RTC 未同步）。"""
        return dt.year == 1970

    def extract_file(self, path: str | Path) -> list[LogEntry]:
        """从 DLT 二进制中提取文本时间戳行。"""
        entries: list[LogEntry] = []
        fname = Path(path).name
        # 从文件名提取时间窗口（用于 epoch 文件的近似定位）
        file_wall_time = self._parse_dlt_filename(fname)

        try:
            with open(path, "rb") as f:
                raw = f.read()
        except OSError:
            return entries

        # 将二进制内容转为文本（忽略不可打印字节）
        text = raw.decode("utf-8", errors="replace")
        for line in text.splitlines():
            m = self._TEXT_TS.search(line)
            if not m:
                continue
            ts_str, source_file, message = m.groups()
            try:
                wall = datetime.strptime(ts_str[:26], "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                continue
            is_epoch = self._is_epoch_time(wall)
            entries.append(LogEntry(
                source="dlt",
                message=f"{source_file}: {message.strip()}",
                wall_time=None if is_epoch else wall,
                raw_time=ts_str,
                # epoch 文件：uptime_ms = 秒数×1000（1970-01-01 HH:MM:SS 就是 uptime）
                uptime_ms=int((wall - self._EPOCH_1970).total_seconds() * 1000) if is_epoch else None,
            ))
        return entries

    @staticmethod
    def _parse_dlt_filename(fname: str) -> datetime | None:
        """
        从 DLT 文件名解析文件创建的真实 UTC 时间。
        格式：dlt_offlinetrace.NNNNNNNNNN.YYYYMMDDHHMMSS.dlt
        示例：dlt_offlinetrace.0000000060.20250910032542.dlt → 2025-09-10 03:25:42
        若为 19700101XXXXXX 则返回 None。
        """
        # 取文件名的时间戳部分（第 3 段）
        parts = fname.rstrip(".dlt").split(".")
        if len(parts) < 3:
            return None
        ts_part = parts[-1]
        if ts_part.startswith("19700101"):
            return None
        try:
            return datetime.strptime(ts_part, "%Y%m%d%H%M%S")
        except ValueError:
            return None


class IbduLogParser:
    """
    解析 iBDU 日志（iBDU_*.txt）。

    行格式：[YYYY.MM.DD HH:MM:SS.mmm]hex_or_text_content
    时间戳为真实绝对时间，可直接用作参考。

    内容部分为十六进制编码的二进制数据，不强制解码；
    仅使用时间戳（含可读标签如 RST:、OG、CPUL 等）。
    """
    _PATTERN = re.compile(
        r'^\[(\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}\.\d{1,3})\](.*)'
    )

    def parse_line(self, line: str) -> LogEntry | None:
        m = self._PATTERN.match(line.rstrip())
        if not m:
            return None
        ts_str, content = m.groups()
        try:
            wall = datetime.strptime(ts_str, "%Y.%m.%d %H:%M:%S.%f")
        except ValueError:
            try:
                wall = datetime.strptime(ts_str, "%Y.%m.%d %H:%M:%S.%f")
            except ValueError:
                return None
        return LogEntry(
            source="ibdu",
            message=content.strip(),
            wall_time=wall,
            raw_time=ts_str,
        )

    def parse_file(self, path: str | Path) -> list[LogEntry]:
        entries: list[LogEntry] = []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                e = self.parse_line(line)
                if e:
                    entries.append(e)
        return entries


# ────────────────────────────────────────────────────────────────────
# 跨域锚点识别（基于真实日志关键事件）
# ────────────────────────────────────────────────────────────────────

# 真实日志中各域的 FOTA 关键事件关键词
# key = 锚点类型，value = {source: [关键词列表（OR关系）]}
REAL_ANCHOR_PATTERNS: dict[str, dict[str, list[str]]] = {
    "fota_mode_set": {
        # MCU : INF@OTA:Utty Rx Cmd: FOTAMODE:3 1 1 60000 1!
        "mcu":    ["@OTA:Utty Rx Cmd: FOTAMODE", "@OTA:FotaModeInfo.Mode"],
        # DLT : fota_api_mcu.cppL[954]: [fota] OnMcuIndication 59
        "dlt":    ["[fota] OnMcuIndication", "fota_api_mcu"],
        # FOTA HMI : [FotaHMIServiceImpl]-showUpgradeResult
        "fota_hmi": ["showUpgradeResult upgradeFlag"],
    },
    "icgm_link_up": {
        # FOTA HMI : [FotaHMIServiceImpl-SOA]-IcgmLinkNotify  LinkSts: 1
        "fota_hmi": ["IcgmLinkNotify  LinkSts: 1", "IcgmLinkNotify LinkSts: 1"],
        # Android  : [MaxusMobileIcgmController] updateMobileNetwork … serviceState = 1
        "android": ["MaxusMobileIcgmController", "updateMobileNetwork"],
    },
    "fota_flash_progress": {
        # DLT  : fota_state_refresh.cppL[1282]: chipName = ZCU_DRAPP, refreshProgress = 100
        "dlt":  ["fota_state_refresh", "refreshProgress"],
        # MCU  : INF@OTA:FotaUpdate mcuPostMessage
        "mcu":  ["@OTA:FotaUpdate mcuPostMessage"],
    },
    "mcu_fota_mode_ack": {
        # MCU : INF@OTA:otaModeHandleGetSigOK
        "mcu": ["@OTA:otaModeHandleGetSigOK"],
        # DLT : fota recv fotaMode = 1
        "dlt": ["fota recv fotaMode"],
    },
}


def _find_first_match(entries: list[LogEntry], keywords: list[str]) -> LogEntry | None:
    for e in entries:
        if any(kw in e.message for kw in keywords):
            return e
    return None


def identify_cross_domain_anchors(
    entries_by_source: dict[str, list[LogEntry]],
) -> list[AnchorEvent]:
    """
    在各域 LogEntry 列表中识别跨域锚点事件。
    只有在 ≥2 个域中均找到匹配且时间差 < 阈值时才认定为有效锚点。
    """
    anchors: list[AnchorEvent] = []
    MAX_DELTA = timedelta(seconds=30)   # 超过 30s 认为不是同一事件

    for event_type, pattern in REAL_ANCHOR_PATTERNS.items():
        matched: dict[str, datetime] = {}

        for source, keywords in pattern.items():
            if source not in entries_by_source:
                continue
            entry = _find_first_match(entries_by_source[source], keywords)
            if entry and entry.wall_time is not None:
                matched[source] = entry.wall_time

        if len(matched) < 2:
            continue

        # 时间一致性检查：所有匹配时间戳之间的极差 < MAX_DELTA
        times = list(matched.values())
        spread = max(times) - min(times)
        if spread > MAX_DELTA:
            continue

        anchors.append(AnchorEvent(
            event_type=event_type,
            description=f"跨域锚点: {event_type}",
            timestamps=matched,
            confidence=0.9 if len(matched) >= 3 else 0.75,
        ))

    return anchors


# ────────────────────────────────────────────────────────────────────
# 时间对齐服务
# ────────────────────────────────────────────────────────────────────

class TimeAlignmentService:
    """
    多域日志时间对齐服务。

    两种入口：
    - align_log_files(log_files)  — 传入文件路径，自动解析并对齐（推荐）
    - align_events(events_by_source) — 传入已解析的 {source: [LogEntry]} 字典
    """

    def __init__(self, reference_source: str = "android") -> None:
        self.reference_source = reference_source

    # ── 高层接口：真实文件 ──────────────────────────────────────────

    def align_log_files(
        self,
        log_files: dict[str, list[str | Path]],
        android_year: int = 2025,
    ) -> AlignmentResult:
        """
        从文件路径解析各域日志，执行时间对齐。

        参数
        ----
        log_files : dict
            {source_type: [file_path, ...]}
            source_type: "android" | "fota_hmi" | "mcu" | "dlt" | "ibdu"
        android_year : int
            Android logcat 无年份，默认补 2025。
        """
        entries_by_source: dict[str, list[LogEntry]] = {}

        mcu_parser = McuLogParser()

        for source, paths in log_files.items():
            all_entries: list[LogEntry] = []
            for path in paths:
                path = Path(path)
                if not path.exists():
                    continue
                if source == "android":
                    all_entries.extend(AndroidLogParser(year=android_year).parse_file(path))
                elif source == "fota_hmi":
                    all_entries.extend(FotaHmiLogParser().parse_file(path))
                elif source == "mcu":
                    if path.suffix == ".gz":
                        all_entries.extend(mcu_parser.parse_tar_gz(path))
                    else:
                        all_entries.extend(mcu_parser.parse_file(path))
                elif source == "dlt":
                    all_entries.extend(DltTextExtractor().extract_file(path))
                elif source == "ibdu":
                    all_entries.extend(IbduLogParser().parse_file(path))
            if all_entries:
                # 按时间排序（wall_time 为 None 的排到末尾）
                all_entries.sort(key=lambda e: e.wall_time or datetime.max)
                entries_by_source[source] = all_entries

        return self.align_events(entries_by_source)

    # ── 核心对齐逻辑 ──────────────────────────────────────────────

    def align_events(
        self,
        events_by_source: dict[str, list[LogEntry]],
    ) -> AlignmentResult:
        """
        对已解析的多域 LogEntry 执行时间对齐。

        对齐策略：
        1. iBDU / 有效 DLT 时间戳已为真实时间，直接作参考
        2. MCU 经过 McuTickAligner 已完成 tick→wall_time，无需外部偏移
        3. FOTA HMI uptime 通过跨域锚点事件计算偏移
        4. DLT epoch 文件通过跨域锚点或相邻文件定位
        """
        warnings: list[str] = []
        offsets: dict[str, ClockOffset] = {}

        # 参考域偏移为 0
        offsets[self.reference_source] = ClockOffset(
            source_type=self.reference_source,
            offset_seconds=0.0,
            confidence=1.0,
            reference_source=self.reference_source,
            anchor_count=0,
        )

        # 1. 识别跨域锚点
        anchor_events = identify_cross_domain_anchors(events_by_source)

        # 2. 对已有 wall_time 的域（mcu/dlt/ibdu），通过锚点计算偏移
        for source in events_by_source:
            if source == self.reference_source:
                continue
            if source in offsets:
                continue

            ref_entries = events_by_source.get(self.reference_source, [])
            src_entries = events_by_source[source]

            offset_samples: list[tuple[float, float]] = []

            # 从跨域锚点提取偏移样本
            for anchor in anchor_events:
                if self.reference_source in anchor.timestamps and source in anchor.timestamps:
                    ref_ts = anchor.timestamps[self.reference_source]
                    src_ts = anchor.timestamps[source]
                    offset_samples.append(
                        ((ref_ts - src_ts).total_seconds(), anchor.confidence)
                    )

            # MCU / DLT / iBDU 已有绝对时间，若与参考时钟在锚点上匹配则直接用
            # 否则认为已对齐（偏移 ≈ 0，低置信度）
            if not offset_samples:
                # 检查该域是否有 wall_time（MCU/DLT/iBDU 正常情况下有）
                has_wall = any(e.wall_time is not None for e in src_entries)
                if has_wall and source in ("mcu", "ibdu", "dlt"):
                    # 有真实时间，置信度中等，偏移按 0 处理
                    offsets[source] = ClockOffset(
                        source_type=source,
                        offset_seconds=0.0,
                        confidence=0.65,
                        reference_source=self.reference_source,
                        anchor_count=0,
                    )
                    warnings.append(
                        f"{source} 域未found跨域锚点，假设与参考时钟对齐（置信度 0.65）"
                    )
                    continue
                else:
                    warnings.append(f"{source} 域无法对齐：缺少 wall_time 且无跨域锚点")
                    continue

            # 加权平均偏移
            total_w = sum(c for _, c in offset_samples)
            weighted = sum(o * c for o, c in offset_samples) / total_w
            confidence = self._calc_confidence(offset_samples)

            offsets[source] = ClockOffset(
                source_type=source,
                offset_seconds=weighted,
                confidence=confidence,
                reference_source=self.reference_source,
                anchor_count=len(offset_samples),
            )

        # 3. FOTA HMI uptime 专项处理：若未通过锚点对齐，尝试启动事件推断
        if "fota_hmi" in events_by_source and "fota_hmi" not in offsets:
            fota_offset = self._align_fota_hmi_uptime(
                events_by_source["fota_hmi"],
                events_by_source,
            )
            if fota_offset is not None:
                offsets["fota_hmi"] = fota_offset
            else:
                warnings.append(
                    "FOTA HMI 无法对齐：2000-01-01 uptime 未找到跨域启动事件匹配"
                )

        # 4. 评估状态
        aligned = set(offsets.keys())
        all_sources = set(events_by_source.keys())
        unaligned = all_sources - aligned
        for src in unaligned:
            warnings.append(f"域 '{src}' 对齐失败")

        high_conf = {s for s, o in offsets.items() if o.confidence >= 0.7}
        if len(unaligned) == 0 and len(high_conf) == len(aligned):
            status = AlignmentStatus.SUCCESS
        elif len(high_conf) >= len(all_sources) * 0.5:
            status = AlignmentStatus.PARTIAL
        else:
            status = AlignmentStatus.FAILED
            warnings.append("⚠️ 整体时间对齐置信度不足，时序结论仅供参考，请人工复核")

        return AlignmentResult(
            status=status,
            offsets=offsets,
            reference_source=self.reference_source,
            anchor_events=anchor_events,
            warnings=warnings,
        )

    # ── FOTA HMI uptime 对齐 ─────────────────────────────────────

    def _align_fota_hmi_uptime(
        self,
        fota_entries: list[LogEntry],
        all_entries: dict[str, list[LogEntry]],
    ) -> ClockOffset | None:
        """
        FOTA HMI 专项：从 IcgmLinkNotify 等事件推算 uptime → 真实时间的偏移。

        FOTA HMI 的 IcgmLinkNotify LinkSts: 1 事件对应 iCGM 连接成功，
        在 Android 日志中可以找到 MaxusMobileIcgmController 等对应事件。
        """
        # FOTA HMI 中找 IcgmLinkNotify 第一次出现
        fota_link = _find_first_match(
            fota_entries,
            ["IcgmLinkNotify  LinkSts: 1", "IcgmLinkNotify LinkSts: 1"],
        )
        if fota_link is None or fota_link.wall_time is None:
            return None

        # Android 中找对应的网络事件
        ref_entries = all_entries.get(self.reference_source, [])
        ref_link = _find_first_match(
            ref_entries,
            ["MaxusMobileIcgmController", "updateMobileNetwork", "ICGM"],
        )
        if ref_link is None or ref_link.wall_time is None:
            # 无法从 Android 找到，尝试 iBDU 时间作参考
            ibdu_first = next(
                (e for e in all_entries.get("ibdu", []) if e.wall_time is not None),
                None,
            )
            if ibdu_first is None:
                return None
            # 粗略：用 iBDU 最早时间 vs FOTA HMI 最早 uptime 估算偏移
            fota_first = next(
                (e for e in fota_entries if e.wall_time is not None),
                None,
            )
            if fota_first is None:
                return None
            offset_s = (ibdu_first.wall_time - fota_first.wall_time).total_seconds()
            return ClockOffset(
                source_type="fota_hmi",
                offset_seconds=offset_s,
                confidence=0.5,
                reference_source=self.reference_source,
                anchor_count=1,
            )

        offset_s = (ref_link.wall_time - fota_link.wall_time).total_seconds()
        return ClockOffset(
            source_type="fota_hmi",
            offset_seconds=offset_s,
            confidence=0.75,
            reference_source=self.reference_source,
            anchor_count=1,
        )

    # ── 内部工具 ──────────────────────────────────────────────────

    @staticmethod
    def _calc_confidence(samples: list[tuple[float, float]]) -> float:
        """基于样本数量和一致性计算置信度。"""
        if not samples:
            return 0.0
        n = len(samples)
        base = min(n / 3.0, 1.0)   # 3 个以上锚点达到满分
        avg_anchor_conf = sum(c for _, c in samples) / n
        offsets = [o for o, _ in samples]
        if n > 1:
            mean = sum(offsets) / n
            std = (sum((o - mean) ** 2 for o in offsets) / n) ** 0.5
            # std > 10s 开始降分，std > 60s 降到 0.4
            consistency = max(0.4, 1.0 - max(0.0, std - 10) / 100)
        else:
            consistency = 0.85
        return min(base * avg_anchor_conf * consistency, 1.0)

