"""真实日志格式解析器测试。"""

from datetime import datetime, timedelta

from services.parser.parser_android import AndroidParser
from services.parser.parser_fota import FotaParser
from services.parser.parser_mcu import MCUParser
from services.parser.parser_dlt import DLTParser
from services.parser.parser_ibdu import IBDUParser
from services.parser.base import EventLevel, EventType, ParserRegistry


def test_android_real_format():
    parser = AndroidParser(year=2025)
    line = "09-12 11:24:22.028403   986   986 W NmeaOperation: nmea data report start"
    event = parser.parse_line(line, 1)
    assert event is not None
    assert event.source_type == "android"
    assert event.level == EventLevel.WARN
    assert event.original_ts == datetime(2025, 9, 12, 11, 24, 22, 28403)


def test_fota_hmi_real_format():
    parser = FotaParser()
    line = (
        "2000-01-01 00:01:09,856 DEBUG (FotaHMIServiceImpl.java:232)- "
        "[FotaHMIServiceImpl-SOA]-IcgmLinkNotify  LinkSts: 1"
    )
    event = parser.parse_line(line, 1)
    assert event is not None
    assert event.source_type == "fota_hmi"
    assert event.level == EventLevel.DEBUG
    assert event.parsed_fields["is_uptime_clock"] is True


def test_mcu_real_format_with_sysdate_anchor(tmp_path):
    parser = MCUParser()
    log = "\n".join([
        "&18869328 INF@SYS:Sys Date: 2025 9 11_4:5:56",
        "&18869330 INF@OTA:Utty Rx Cmd: FOTAMODE:3 1 1 60000 1!",
    ])
    p = tmp_path / "MCU_test.txt"
    p.write_text(log, encoding="utf-8")

    events = list(parser.parse_file(p))
    assert len(events) == 2
    fota_event = events[1]
    assert fota_event.event_type == EventType.FOTA_STAGE
    assert fota_event.original_ts == datetime(2025, 9, 11, 4, 5, 56, 2000)


def test_dlt_real_embedded_timestamp(tmp_path):
    parser = DLTParser()
    line = (
        "2025-09-11 00:05:52.391679:fota_state_refresh.cppL[1282] "
        "tid:[23456]:chipName = ZCU_DRAPP, refreshProgress = 100"
    )
    p = tmp_path / "dlt_offlinetrace.0000000060.20250910032542.dlt"
    p.write_bytes(("\x00" + line + "\x00").encode("utf-8", errors="ignore"))

    events = list(parser.parse_file(p))
    assert len(events) == 1
    e = events[0]
    assert e.source_type == "dlt"
    assert e.event_type == EventType.FOTA_STAGE
    assert e.parsed_fields["is_epoch_clock"] is False


def test_ibdu_real_format():
    parser = IBDUParser()
    line = "[2025.09.11 04:05:55.100]RST:00 00 00 00 86 0E 00 00 96 10"
    event = parser.parse_line(line, 1)
    assert event is not None
    assert event.source_type == "ibdu"
    assert event.original_ts == datetime(2025, 9, 11, 4, 5, 55, 100000)


def test_parser_registry_contains_real_types():
    registry = ParserRegistry()
    registry.register("android", AndroidParser)
    registry.register("fota_hmi", FotaParser)
    registry.register("mcu", MCUParser)
    registry.register("dlt", DLTParser)
    registry.register("ibdu", IBDUParser)

    assert registry.get_parser("android") is not None
    assert registry.get_parser("fota_hmi") is not None
    assert registry.get_parser("mcu") is not None
    assert registry.get_parser("dlt") is not None
    assert registry.get_parser("ibdu") is not None
