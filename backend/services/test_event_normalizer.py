"""Event Normalizer tests using real log semantics."""

from datetime import datetime

from services.event_normalizer import (
    EventNormalizer,
    EventCategory,
    FotaStage,
    ErrorSeverity,
)


class TestEventNormalizer:
    def setup_method(self):
        self.normalizer = EventNormalizer()

    def test_normalize_fota_hmi_icgm_event(self):
        parsed_event = {
            "source_type": "fota_hmi",
            "timestamp": datetime(2025, 9, 11, 4, 5, 56),
            "module": "FotaHMIServiceImpl-SOA",
            "level": "DEBUG",
            "message": "IcgmLinkNotify  LinkSts: 1",
            "raw": "2000-01-01 00:01:09,856 DEBUG ...",
            "tag": "FotaHMIServiceImpl-SOA",
        }
        normalized = self.normalizer.normalize_event(
            parsed_event=parsed_event,
            case_id="CASE001",
            file_id="FILE001",
            normalized_ts=datetime(2025, 9, 11, 4, 5, 56),
            clock_confidence=0.9,
        )
        assert normalized is not None
        assert normalized.category == EventCategory.NETWORK
        assert normalized.severity == ErrorSeverity.INFO
        assert "module_fotahmiserviceimpl-soa" in normalized.tags

    def test_normalize_fota_progress_dlt_event(self):
        parsed_event = {
            "source_type": "dlt",
            "timestamp": datetime(2025, 9, 11, 4, 10, 0),
            "module": "fota_state_refresh",
            "level": "INFO",
            "message": "chipName = ZCU_DRAPP, refreshProgress = 45",
            "raw": "2025-09-11 ...",
            "parsed_fields": {"source_file": "fota_state_refresh.cpp"},
        }
        normalized = self.normalizer.normalize_event(
            parsed_event=parsed_event,
            case_id="CASE001",
            file_id="FILE001",
            normalized_ts=datetime(2025, 9, 11, 4, 10, 0),
            clock_confidence=0.95,
        )
        assert normalized is not None
        assert normalized.category == EventCategory.FOTA_LIFECYCLE
        assert normalized.fota_stage == FotaStage.DOWNLOAD
        assert normalized.fota_progress == 45.0

    def test_error_severity_classification(self):
        parsed_event = {
            "source_type": "mcu",
            "timestamp": datetime(2025, 9, 11, 4, 11, 0),
            "module": "OTA",
            "level": "ERROR",
            "message": "flash failed with error code NET_TIMEOUT",
            "raw": "&18870000 ERR@OTA:flash failed...",
        }
        normalized = self.normalizer.normalize_event(
            parsed_event=parsed_event,
            case_id="CASE001",
            file_id="FILE001",
            normalized_ts=datetime(2025, 9, 11, 4, 11, 0),
            clock_confidence=0.8,
        )
        assert normalized is not None
        assert normalized.severity == ErrorSeverity.HIGH
        assert normalized.error_code == "NET_TIMEOUT"

    def test_noise_filtering(self):
        noise_event = {
            "source_type": "android",
            "timestamp": datetime(2025, 9, 11, 4, 0, 0),
            "module": "HeartbeatService",
            "level": "DEBUG",
            "message": "heartbeat tick",
            "raw": "heartbeat tick",
        }
        normalized = self.normalizer.normalize_event(
            parsed_event=noise_event,
            case_id="CASE001",
            file_id="FILE001",
            normalized_ts=datetime(2025, 9, 11, 4, 0, 0),
            clock_confidence=1.0,
        )
        assert normalized is None

    def test_fota_stage_identification_real_keywords(self):
        assert self.normalizer._identify_fota_stage("service onCreate") == FotaStage.INIT
        assert self.normalizer._identify_fota_stage("refreshProgress = 100") == FotaStage.DOWNLOAD
        assert self.normalizer._identify_fota_stage("Signature verify failed") == FotaStage.VERIFY
        assert self.normalizer._identify_fota_stage("flash writing partition") == FotaStage.INSTALL
        assert self.normalizer._identify_fota_stage("showUpgradeResult upgradeFlag : Idle") == FotaStage.COMPLETE

    def test_batch_normalization(self):
        parsed_events = [
            {
                "source_type": "android",
                "timestamp": datetime(2025, 9, 11, 4, 3, 23),
                "module": "ActivityManager",
                "level": "INFO",
                "message": "Start proc com.saicmotor.fotahmiservice pid:23456",
                "raw": "09-11 04:03:23.521000 ...",
            },
            {
                "source_type": "fota_hmi",
                "timestamp": datetime(2025, 9, 11, 4, 5, 56),
                "module": "FotaHMIServiceImpl-SOA",
                "level": "DEBUG",
                "message": "IcgmLinkNotify  LinkSts: 1",
                "raw": "2000-01-01 ...",
            },
        ]
        time_alignment_result = {
            "offsets": {
                "android": {"offset_seconds": 0.0, "confidence": 0.99},
                "fota_hmi": {"offset_seconds": 5.0, "confidence": 0.8},
            }
        }
        normalized = self.normalizer.normalize_batch(
            parsed_events=parsed_events,
            case_id="CASE001",
            file_id="FILE001",
            time_alignment_result=time_alignment_result,
        )
        assert len(normalized) == 2
        assert normalized[1].clock_confidence == 0.8

    def test_category_classification(self):
        assert self.normalizer._classify_category("IcgmLinkNotify LinkSts: 1", "FotaHMIServiceImpl") == EventCategory.NETWORK
        assert self.normalizer._classify_category("Utty Rx Cmd: FOTAMODE:3", "OTA") == EventCategory.FOTA_LIFECYCLE
        assert self.normalizer._classify_category("Sys Date: 2025 9 11_4:5:56", "SYS") == EventCategory.SYSTEM_STATE

