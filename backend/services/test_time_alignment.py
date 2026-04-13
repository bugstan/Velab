"""
test_time_alignment.py — 时间对齐服务单元测试

所有测试均基于真实车端日志格式（不使用虚构的英文关键词），覆盖：
  1. MCU tick → wall_time 转换（Sys Date 锚点）
  2. Android logcat 解析（MM-DD 无年份）
  3. FOTA HMI uptime 解析（2000-01-01 基点）
  4. DLT 文本提取（valid 与 epoch 两种时间戳）
  5. iBDU 绝对时间解析
  6. 跨域锚点识别（IcgmLinkNotify 等真实事件）
  7. align_events() 端到端对齐
"""

import pytest
from datetime import datetime, timedelta
from services.time_alignment import (
    AlignmentStatus,
    AlignmentResult,
    ClockOffset,
    LogEntry,
    McuSysDateAnchor,
    McuTickAligner,
    AndroidLogParser,
    FotaHmiLogParser,
    McuLogParser,
    DltTextExtractor,
    IbduLogParser,
    TimeAlignmentService,
    identify_cross_domain_anchors,
    REAL_ANCHOR_PATTERNS,
)


# ────────────────────────────────────────────────────────────────────
# MCU Tick Aligner
# ────────────────────────────────────────────────────────────────────

class TestMcuTickAligner:

    MCU_LINE_1 = "&18869328 INF@SYS:Sys Date: 2025 9 11_4:5:56"
    MCU_LINE_2 = "&18929348 INF@SYS:Sys Date: 2025 9 11_4:6:56"

    def _make_aligner(self):
        aligner = McuTickAligner()
        aligner.feed_line(self.MCU_LINE_1)
        aligner.feed_line(self.MCU_LINE_2)
        return aligner

    def test_feed_line_extracts_anchor(self):
        aligner = McuTickAligner()
        anchor = aligner.feed_line(self.MCU_LINE_1)
        assert anchor is not None
        assert anchor.tick_ms == 18869328
        assert anchor.wall_time == datetime(2025, 9, 11, 4, 5, 56)

    def test_non_sysdate_line_returns_none(self):
        aligner = McuTickAligner()
        result = aligner.feed_line("&18854647 INF@COM:T:c0b1:356")
        assert result is None

    def test_tick_to_wall_time_at_anchor(self):
        aligner = self._make_aligner()
        t = aligner.tick_to_wall_time(18869328)
        assert t == datetime(2025, 9, 11, 4, 5, 56)

    def test_tick_to_wall_time_forward_interpolation(self):
        aligner = self._make_aligner()
        t = aligner.tick_to_wall_time(18869328 + 5000)
        expected = datetime(2025, 9, 11, 4, 5, 56) + timedelta(seconds=5)
        assert t == expected

    def test_tick_to_wall_time_backward_interpolation(self):
        aligner = self._make_aligner()
        t = aligner.tick_to_wall_time(18869328 - 1000)
        expected = datetime(2025, 9, 11, 4, 5, 56) - timedelta(seconds=1)
        assert t == expected

    def test_anchor_interval_is_60s(self):
        aligner = self._make_aligner()
        t1 = aligner.tick_to_wall_time(18869328)
        t2 = aligner.tick_to_wall_time(18929348)
        assert t2 - t1 == timedelta(seconds=60)

    def test_no_anchor_returns_none(self):
        aligner = McuTickAligner()
        assert aligner.tick_to_wall_time(12345) is None

    def test_extended_sysdate_format(self):
        aligner = McuTickAligner()
        anchor = aligner.feed_line(
            "&18869426 INF@SYS:Sys Date: 2025 9 11_4:5:56(179726756 777)"
        )
        assert anchor is not None
        assert anchor.tick_ms == 18869426
        assert anchor.wall_time == datetime(2025, 9, 11, 4, 5, 56)


# ────────────────────────────────────────────────────────────────────
# Android Log Parser
# ────────────────────────────────────────────────────────────────────

class TestAndroidLogParser:

    SAMPLE_LINE = (
        "09-12 11:24:22.028403   986   986 W NmeaOperation: "
        "nmea data report start "
    )
    FOTA_PROC_LINE = (
        "09-11 04:03:23.521000 12345 12345 I ActivityManager: "
        "Start proc com.saicmotor.fotahmiservice pid:23456"
    )

    def test_parse_valid_line(self):
        parser = AndroidLogParser(year=2025)
        entry = parser.parse_line(self.SAMPLE_LINE)
        assert entry is not None
        assert entry.source == "android"
        assert entry.wall_time == datetime(2025, 9, 12, 11, 24, 22, 28403)
        assert "NmeaOperation" in entry.message

    def test_default_year_injection(self):
        parser = AndroidLogParser(year=2025)
        entry = parser.parse_line(self.SAMPLE_LINE)
        assert entry.wall_time.year == 2025

    def test_custom_year_injection(self):
        parser = AndroidLogParser(year=2024)
        entry = parser.parse_line(self.SAMPLE_LINE)
        assert entry.wall_time.year == 2024

    def test_fota_process_line(self):
        parser = AndroidLogParser(year=2025)
        entry = parser.parse_line(self.FOTA_PROC_LINE)
        assert entry is not None
        assert "fotahmiservice" in entry.message.lower()

    def test_invalid_line_returns_none(self):
        parser = AndroidLogParser()
        assert parser.parse_line("") is None
        assert parser.parse_line("some random text") is None
        assert parser.parse_line("&18869328 INF@SYS:Sys Date: 2025 9 11_4:5:56") is None

    def test_microsecond_precision(self):
        parser = AndroidLogParser(year=2025)
        entry = parser.parse_line(self.SAMPLE_LINE)
        assert entry.wall_time.microsecond == 28403

    def test_missing_ntp_line(self):
        parser = AndroidLogParser(year=2025)
        line = "09-11 04:01:00.000000   500   500 W GnssService: Missing NTP fix"
        entry = parser.parse_line(line)
        assert entry is not None
        assert "Missing NTP" in entry.message


# ────────────────────────────────────────────────────────────────────
# FOTA HMI Log Parser
# ────────────────────────────────────────────────────────────────────

class TestFotaHmiLogParser:

    INIT_LINE = (
        "2000-01-01 00:01:05,770 DEBUG (Log.java:45)- "
        "[utils_Log]-init log end"
    )
    ICGM_LINK_LINE = (
        "2000-01-01 00:01:09,856 DEBUG (FotaHMIServiceImpl.java:232)- "
        "[FotaHMIServiceImpl-SOA]-IcgmLinkNotify  LinkSts: 1"
    )
    SERVICE_START_LINE = (
        "2000-01-01 00:01:05,521 INFO  (FOTAHMIService.java:100)- "
        "[FOTAHMIService]-service onCreate"
    )
    UPGRADE_RESULT_LINE = (
        "2000-01-01 00:30:00,000 INFO  (FotaHMIServiceImpl.java:500)- "
        "[FotaHMIServiceImpl]-showUpgradeResult upgradeFlag : Idle"
    )

    def test_parse_init_line(self):
        parser = FotaHmiLogParser()
        entry = parser.parse_line(self.INIT_LINE)
        assert entry is not None
        assert entry.source == "fota_hmi"
        assert entry.uptime_ms == 65770

    def test_parse_icgm_link_line(self):
        parser = FotaHmiLogParser()
        entry = parser.parse_line(self.ICGM_LINK_LINE)
        assert entry is not None
        assert "IcgmLinkNotify" in entry.message
        assert "LinkSts: 1" in entry.message

    def test_service_start_line(self):
        parser = FotaHmiLogParser()
        entry = parser.parse_line(self.SERVICE_START_LINE)
        assert entry is not None
        assert "FOTAHMIService" in entry.message

    def test_upgrade_result_line(self):
        parser = FotaHmiLogParser()
        entry = parser.parse_line(self.UPGRADE_RESULT_LINE)
        assert entry is not None
        assert "showUpgradeResult" in entry.message

    def test_wall_time_is_2000_base(self):
        parser = FotaHmiLogParser()
        entry = parser.parse_line(self.INIT_LINE)
        assert entry.wall_time.year == 2000
        assert entry.wall_time.month == 1
        assert entry.wall_time.day == 1

    def test_uptime_calculation(self):
        parser = FotaHmiLogParser()
        entry = parser.parse_line(self.ICGM_LINK_LINE)
        assert entry.uptime_ms == 69856

    def test_invalid_line_returns_none(self):
        parser = FotaHmiLogParser()
        assert parser.parse_line("") is None
        assert parser.parse_line("some text") is None


# ────────────────────────────────────────────────────────────────────
# MCU Log Parser
# ────────────────────────────────────────────────────────────────────

class TestMcuLogParser:

    MCU_LINES = [
        "&18854647 INF@COM:T:c0b1:356",
        "&18869328 INF@SYS:Sys Date: 2025 9 11_4:5:56",
        "&18869330 INF@OTA:Utty Rx Cmd: FOTAMODE:3 1 1 60000 1!",
        "&18870000 INF@OTA:FotaModeInfo.Mode = 3",
        "&18929348 INF@SYS:Sys Date: 2025 9 11_4:6:56",
    ]

    def test_tick_aligner_has_anchors_after_parse(self, tmp_path):
        log_file = tmp_path / "MCU_test.txt"
        log_file.write_text("\n".join(self.MCU_LINES) + "\n", encoding="utf-8")
        parser = McuLogParser()
        parser.parse_file(log_file)
        assert len(parser.tick_aligner.anchors) == 2

    def test_entries_have_wall_time_after_parse(self, tmp_path):
        log_file = tmp_path / "MCU_test.txt"
        log_file.write_text("\n".join(self.MCU_LINES) + "\n", encoding="utf-8")
        parser = McuLogParser()
        entries = parser.parse_file(log_file)
        for e in entries:
            assert e.wall_time is not None, f"wall_time missing for: {e.message}"

    def test_fota_mode_entry_time(self, tmp_path):
        log_file = tmp_path / "MCU_test.txt"
        log_file.write_text("\n".join(self.MCU_LINES) + "\n", encoding="utf-8")
        parser = McuLogParser()
        entries = parser.parse_file(log_file)
        fota_entry = next(e for e in entries if "FOTAMODE" in e.message)
        expected = datetime(2025, 9, 11, 4, 5, 56) + timedelta(milliseconds=2)
        assert fota_entry.wall_time == expected

    def test_source_is_mcu(self, tmp_path):
        log_file = tmp_path / "MCU_test.txt"
        log_file.write_text(self.MCU_LINES[2] + "\n", encoding="utf-8")
        parser = McuLogParser()
        entries = parser.parse_file(log_file)
        for e in entries:
            assert e.source == "mcu"


# ────────────────────────────────────────────────────────────────────
# DLT Text Extractor
# ────────────────────────────────────────────────────────────────────

class TestDltTextExtractor:

    VALID_TS_LINE = (
        "2025-09-11 00:05:52.391679:fota_state_refresh.cppL[1282] "
        "tid:[23456]:chipName = ZCU_DRAPP, refreshProgress = 100"
    )
    EPOCH_TS_LINE = (
        "1970-01-01 00:00:55.619666:fota_api_mcu.cppL[954] "
        "tid:[11111]:[fota] OnMcuIndication 59"
    )

    def _fake_dlt(self, line: str) -> bytes:
        return b"\x00\x01\x02" + line.encode("utf-8") + b"\x00\x03"

    def test_extract_valid_timestamp(self, tmp_path):
        dlt_file = tmp_path / "dlt_offlinetrace.0000000060.20250910032542.dlt"
        dlt_file.write_bytes(self._fake_dlt(self.VALID_TS_LINE))
        entries = DltTextExtractor().extract_file(dlt_file)
        assert len(entries) == 1
        e = entries[0]
        assert e.source == "dlt"
        assert e.wall_time is not None
        assert e.wall_time.year == 2025
        assert e.uptime_ms is None

    def test_extract_epoch_timestamp(self, tmp_path):
        dlt_file = tmp_path / "dlt_offlinetrace.0000000001.19700101000049.dlt"
        dlt_file.write_bytes(self._fake_dlt(self.EPOCH_TS_LINE))
        entries = DltTextExtractor().extract_file(dlt_file)
        assert len(entries) == 1
        e = entries[0]
        assert e.wall_time is None
        assert e.uptime_ms is not None
        assert e.uptime_ms == 55619

    def test_fota_mcu_indication_extracted(self, tmp_path):
        dlt_file = tmp_path / "dlt_offlinetrace.0000000001.19700101000049.dlt"
        dlt_file.write_bytes(self._fake_dlt(self.EPOCH_TS_LINE))
        entries = DltTextExtractor().extract_file(dlt_file)
        assert any("[fota] OnMcuIndication" in e.message for e in entries)

    def test_parse_dlt_filename_valid(self):
        dt = DltTextExtractor._parse_dlt_filename(
            "dlt_offlinetrace.0000000060.20250910032542.dlt"
        )
        assert dt == datetime(2025, 9, 10, 3, 25, 42)

    def test_parse_dlt_filename_epoch(self):
        dt = DltTextExtractor._parse_dlt_filename(
            "dlt_offlinetrace.0000000001.19700101000049.dlt"
        )
        assert dt is None

    def test_empty_dlt_file(self, tmp_path):
        dlt_file = tmp_path / "empty.dlt"
        dlt_file.write_bytes(b"")
        entries = DltTextExtractor().extract_file(dlt_file)
        assert entries == []


# ────────────────────────────────────────────────────────────────────
# iBDU Log Parser
# ────────────────────────────────────────────────────────────────────

class TestIbduLogParser:

    SAMPLE_LINE = "[2025.09.11 04:05:55.100]RST:00 00 00 00 86 0E 00 00 96 10"
    ANOTHER_LINE = "[2025.09.11 04:06:10.250]OG 82 01 00 01 01 00 01 00 00 00 00 00 23"

    def test_parse_valid_line(self):
        parser = IbduLogParser()
        entry = parser.parse_line(self.SAMPLE_LINE)
        assert entry is not None
        assert entry.source == "ibdu"
        assert entry.wall_time == datetime(2025, 9, 11, 4, 5, 55, 100000)

    def test_wall_time_is_absolute(self):
        parser = IbduLogParser()
        entry = parser.parse_line(self.SAMPLE_LINE)
        assert entry.wall_time.year == 2025
        assert entry.wall_time.month == 9

    def test_time_delta_between_lines(self):
        parser = IbduLogParser()
        e1 = parser.parse_line(self.SAMPLE_LINE)
        e2 = parser.parse_line(self.ANOTHER_LINE)
        assert e1 is not None and e2 is not None
        delta = e2.wall_time - e1.wall_time
        assert abs(delta.total_seconds() - 15.15) < 0.001

    def test_content_preserved_in_message(self):
        parser = IbduLogParser()
        entry = parser.parse_line(self.SAMPLE_LINE)
        assert "RST" in entry.message

    def test_invalid_line_returns_none(self):
        parser = IbduLogParser()
        assert parser.parse_line("") is None
        assert parser.parse_line("just some text") is None
        assert parser.parse_line("09-11 04:05:55.100000  986  986 W Tag: msg") is None


# ────────────────────────────────────────────────────────────────────
# 跨域锚点识别
# ────────────────────────────────────────────────────────────────────

class TestCrossDomainAnchorIdentification:

    def _e(self, source, wall_time, message):
        return LogEntry(source=source, message=message, wall_time=wall_time, raw_time="")

    def test_icgm_link_up_anchor_identified(self):
        base = datetime(2025, 9, 11, 4, 5, 56)
        entries_by_source = {
            "fota_hmi": [self._e("fota_hmi", base,
                "[FotaHMIServiceImpl-SOA]-IcgmLinkNotify  LinkSts: 1")],
            "android":  [self._e("android", base + timedelta(seconds=1),
                "MaxusMobileIcgmController updateMobileNetwork serviceState = 1")],
        }
        anchors = identify_cross_domain_anchors(entries_by_source)
        assert any(a.event_type == "icgm_link_up" for a in anchors)

    def test_fota_mode_anchor_identified(self):
        base = datetime(2025, 9, 11, 4, 6, 0)
        entries_by_source = {
            "mcu": [self._e("mcu", base,
                "@OTA:Utty Rx Cmd: FOTAMODE:3 1 1 60000 1!")],
            "dlt": [self._e("dlt", base + timedelta(seconds=2),
                "fota_api_mcu.cppL[954]: [fota] OnMcuIndication 59")],
        }
        anchors = identify_cross_domain_anchors(entries_by_source)
        assert any(a.event_type == "fota_mode_set" for a in anchors)

    def test_time_gap_too_large_excluded(self):
        base = datetime(2025, 9, 11, 4, 5, 56)
        entries_by_source = {
            "fota_hmi": [self._e("fota_hmi", base,
                "[FotaHMIServiceImpl-SOA]-IcgmLinkNotify  LinkSts: 1")],
            "android":  [self._e("android", base + timedelta(seconds=60),
                "MaxusMobileIcgmController updateMobileNetwork")],
        }
        anchors = identify_cross_domain_anchors(entries_by_source)
        assert not any(a.event_type == "icgm_link_up" for a in anchors)

    def test_three_domain_anchor_confidence(self):
        base = datetime(2025, 9, 11, 4, 6, 0)
        entries_by_source = {
            "mcu":      [self._e("mcu", base,
                "@OTA:Utty Rx Cmd: FOTAMODE:3 1 1 60000 1!")],
            "dlt":      [self._e("dlt", base + timedelta(seconds=1),
                "fota_api_mcu.cppL[1]: [fota] OnMcuIndication 59")],
            "fota_hmi": [self._e("fota_hmi", base + timedelta(seconds=2),
                "showUpgradeResult upgradeFlag = Idle")],
        }
        anchors = identify_cross_domain_anchors(entries_by_source)
        for a in anchors:
            if a.event_type == "fota_mode_set":
                assert a.confidence >= 0.9


# ────────────────────────────────────────────────────────────────────
# TimeAlignmentService 端到端
# ────────────────────────────────────────────────────────────────────

class TestTimeAlignmentServiceEndToEnd:

    def _e(self, source, wall_time, message):
        return LogEntry(source=source, message=message, wall_time=wall_time, raw_time="")

    def test_android_is_reference_offset_zero(self):
        service = TimeAlignmentService(reference_source="android")
        base = datetime(2025, 9, 11, 4, 5, 56)
        result = service.align_events({
            "android": [self._e("android", base, "some android event")],
            "mcu":     [self._e("mcu", base, "@OTA:Utty Rx Cmd: FOTAMODE:3 1 1 60000 1!")],
        })
        assert result.offsets["android"].offset_seconds == 0.0

    def test_ibdu_source_default_offset_zero(self):
        service = TimeAlignmentService(reference_source="android")
        base = datetime(2025, 9, 11, 4, 5, 56)
        result = service.align_events({
            "android": [self._e("android", base, "some event")],
            "ibdu":    [self._e("ibdu", base + timedelta(seconds=1), "RST:00")],
        })
        assert "ibdu" in result.offsets
        assert result.offsets["ibdu"].offset_seconds == 0.0

    def test_cross_domain_offset_calculated(self):
        service = TimeAlignmentService(reference_source="android")
        base = datetime(2025, 9, 11, 4, 5, 56)
        result = service.align_events({
            "android": [self._e("android", base,
                "MaxusMobileIcgmController updateMobileNetwork")],
            "fota_hmi": [self._e("fota_hmi", base - timedelta(seconds=5),
                "[FotaHMIServiceImpl-SOA]-IcgmLinkNotify  LinkSts: 1")],
        })
        assert "fota_hmi" in result.offsets
        assert abs(result.offsets["fota_hmi"].offset_seconds - 5.0) < 0.1

    def test_get_normalized_timestamp(self):
        result = AlignmentResult(
            status=AlignmentStatus.SUCCESS,
            offsets={
                "mcu": ClockOffset(
                    source_type="mcu",
                    offset_seconds=10.0,
                    confidence=0.95,
                    reference_source="android",
                    anchor_count=2,
                )
            },
            reference_source="android",
            anchor_events=[],
        )
        original = datetime(2025, 9, 11, 4, 5, 50)
        normalized, conf = result.get_normalized_timestamp("mcu", original)
        assert normalized == datetime(2025, 9, 11, 4, 6, 0)
        assert conf == 0.95

    def test_get_normalized_timestamp_unknow_domain(self):
        result = AlignmentResult(
            status=AlignmentStatus.PARTIAL,
            offsets={},
            reference_source="android",
            anchor_events=[],
        )
        original = datetime(2025, 9, 11, 4, 5, 50)
        normalized, conf = result.get_normalized_timestamp("unknown", original)
        assert normalized == original
        assert conf == 0.0

    def test_align_log_files_skips_missing_files(self, tmp_path):
        service = TimeAlignmentService()
        result = service.align_log_files({
            "android": [str(tmp_path / "nonexistent.log")],
        })
        assert result is not None
        assert isinstance(result.status, AlignmentStatus)


# ────────────────────────────────────────────────────────────────────
# REAL_ANCHOR_PATTERNS 配置完整性
# ────────────────────────────────────────────────────────────────────

class TestAnchorPatternsConfig:

    def test_required_anchor_types_present(self):
        required = {"fota_mode_set", "icgm_link_up", "fota_flash_progress"}
        assert required.issubset(set(REAL_ANCHOR_PATTERNS.keys()))

    def test_each_anchor_has_at_least_two_sources(self):
        for anchor_type, sources in REAL_ANCHOR_PATTERNS.items():
            assert len(sources) >= 2, f"锚点 '{anchor_type}' 需要 ≥2 个域"

    def test_keywords_are_nonempty_strings(self):
        for anchor_type, sources in REAL_ANCHOR_PATTERNS.items():
            for source, keywords in sources.items():
                assert isinstance(keywords, list) and len(keywords) > 0
                for kw in keywords:
                    assert isinstance(kw, str) and len(kw) > 0

    def test_mcu_pattern_uses_at_module_prefix(self):
        mcu_keywords = []
        for anchor_type, sources in REAL_ANCHOR_PATTERNS.items():
            mcu_keywords.extend(sources.get("mcu", []))
        assert all(kw.startswith("@") for kw in mcu_keywords)
