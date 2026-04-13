"""基础 parser 验证（真实日志格式）。"""

from datetime import datetime
from pathlib import Path
import tempfile

from services.parser import registry
from services.parser.parser_android import AndroidParser
from services.parser.parser_fota import FotaParser


def test_android_parser_real_log():
    test_log = (
        "09-11 04:03:23.521000 12345 12345 I ActivityManager: Start proc com.saicmotor.fotahmiservice pid:23456\n"
        "09-11 04:03:24.100000 12345 12345 W GnssService: Missing NTP fix\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        f.write(test_log)
        temp_path = Path(f.name)

    try:
        parser = AndroidParser(year=2025)
        events = list(parser.parse_file(temp_path))
        assert len(events) == 2
        assert events[0].module == "ActivityManager"
        assert events[1].level.value == "WARN"
    finally:
        temp_path.unlink()


def test_fota_hmi_parser_real_log():
    test_log = (
        "2000-01-01 00:01:05,521 INFO  (FOTAHMIService.java:100)- [FOTAHMIService]-service onCreate\n"
        "2000-01-01 00:01:09,856 DEBUG (FotaHMIServiceImpl.java:232)- [FotaHMIServiceImpl-SOA]-IcgmLinkNotify  LinkSts: 1\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        f.write(test_log)
        temp_path = Path(f.name)

    try:
        parser = FotaParser()
        events = list(parser.parse_file(temp_path))
        assert len(events) == 2
        assert events[0].source_type == "fota_hmi"
        assert events[1].parsed_fields["is_uptime_clock"] is True
    finally:
        temp_path.unlink()


def test_time_window_filtering_fota_hmi():
    test_log = (
        "2000-01-01 00:01:00,000 INFO  (A.java:1)- [FOTA]-Event1\n"
        "2000-01-01 00:02:00,000 INFO  (A.java:1)- [FOTA]-Event2\n"
        "2000-01-01 00:03:00,000 INFO  (A.java:1)- [FOTA]-Event3\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        f.write(test_log)
        temp_path = Path(f.name)

    try:
        parser = FotaParser()
        time_window = (
            datetime(2000, 1, 1, 0, 1, 30),
            datetime(2000, 1, 1, 0, 2, 30),
        )
        events = list(parser.parse_file(temp_path, time_window=time_window))
        assert len(events) == 1
        assert events[0].message == "Event2"
    finally:
        temp_path.unlink()


def test_parser_registry_real_types():
    supported_types = registry.list_supported_types()
    assert "android" in supported_types
    assert "fota_hmi" in supported_types
