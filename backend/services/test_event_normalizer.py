"""
Event Normalizer Service 测试
"""

import unittest
from datetime import datetime
from event_normalizer import (
    EventNormalizer,
    EventCategory,
    FotaStage,
    ErrorSeverity,
    NormalizedEvent
)


class TestEventNormalizer(unittest.TestCase):
    
    def setUp(self):
        """每个测试前初始化"""
        self.normalizer = EventNormalizer()
    
    def test_normalize_fota_event(self):
        """测试FOTA事件标准化"""
        parsed_event = {
            'source_type': 'android',
            'timestamp': datetime(2024, 1, 1, 10, 0, 0),
            'module': 'FotaDownloadImpl',
            'level': 'INFO',
            'message': 'FOTA download started, version 2.1.0, progress 0%',
            'raw': '01-01 10:00:00.000  1234  5678 I FotaDownloadImpl: FOTA download started',
            'pid': 1234,
            'tid': 5678,
            'tag': 'FotaDownloadImpl'
        }
        
        normalized = self.normalizer.normalize_event(
            parsed_event=parsed_event,
            case_id='CASE001',
            file_id='FILE001',
            normalized_ts=datetime(2024, 1, 1, 10, 0, 0),
            clock_confidence=0.95
        )
        
        self.assertIsNotNone(normalized)
        self.assertEqual(normalized.case_id, 'CASE001')
        self.assertEqual(normalized.category, EventCategory.FOTA_LIFECYCLE)
        self.assertEqual(normalized.fota_stage, FotaStage.DOWNLOAD)
        self.assertEqual(normalized.fota_version, '2.1.0')
        self.assertEqual(normalized.fota_progress, 0.0)
        self.assertEqual(normalized.severity, ErrorSeverity.INFO)
        self.assertIn('fota_download', normalized.tags)
    
    def test_normalize_error_event(self):
        """测试错误事件标准化"""
        parsed_event = {
            'source_type': 'android',
            'timestamp': datetime(2024, 1, 1, 10, 5, 0),
            'module': 'NetworkManager',
            'level': 'ERROR',
            'message': 'Connection failed with error code NET_TIMEOUT',
            'raw': '01-01 10:05:00.000  1234  5678 E NetworkManager: Connection failed',
        }
        
        normalized = self.normalizer.normalize_event(
            parsed_event=parsed_event,
            case_id='CASE001',
            file_id='FILE001',
            normalized_ts=datetime(2024, 1, 1, 10, 5, 0),
            clock_confidence=0.95
        )
        
        self.assertIsNotNone(normalized)
        self.assertEqual(normalized.category, EventCategory.NETWORK)
        self.assertEqual(normalized.severity, ErrorSeverity.HIGH)
        self.assertEqual(normalized.error_code, 'NET_TIMEOUT')
        self.assertIn('high_priority', normalized.tags)
    
    def test_noise_filtering(self):
        """测试噪音过滤"""
        # 心跳日志应该被过滤
        noise_event = {
            'source_type': 'android',
            'timestamp': datetime(2024, 1, 1, 10, 0, 0),
            'module': 'HeartbeatService',
            'level': 'DEBUG',
            'message': 'DEBUG: heartbeat tick',
            'raw': '01-01 10:00:00.000  1234  5678 D HeartbeatService: heartbeat tick',
        }
        
        normalized = self.normalizer.normalize_event(
            parsed_event=noise_event,
            case_id='CASE001',
            file_id='FILE001',
            normalized_ts=datetime(2024, 1, 1, 10, 0, 0),
            clock_confidence=0.95
        )
        
        self.assertIsNone(normalized)  # 应该被过滤
    
    def test_fota_stage_identification(self):
        """测试FOTA阶段识别"""
        test_cases = [
            ('FOTA initialization started', FotaStage.INIT),
            ('Checking version with server', FotaStage.VERSION_CHECK),
            ('Download package from server', FotaStage.DOWNLOAD),
            ('Verify package signature', FotaStage.VERIFY),
            ('Installing update package', FotaStage.INSTALL),
            ('System reboot required', FotaStage.REBOOT),
            ('FOTA update completed successfully', FotaStage.COMPLETE),
            ('FOTA update failed', FotaStage.FAILED),
        ]
        
        for message, expected_stage in test_cases:
            stage = self.normalizer._identify_fota_stage(message)
            self.assertEqual(stage, expected_stage, f"Failed for message: {message}")
    
    def test_version_extraction(self):
        """测试版本号提取"""
        test_cases = [
            ('Update to version 2.1.0', '2.1.0'),
            ('Current version: v1.2.3', '1.2.3'),
            ('Build 10.20.30.40', '10.20.30.40'),
            ('No version here', None),
        ]
        
        for message, expected_version in test_cases:
            version = self.normalizer._extract_version(message)
            self.assertEqual(version, expected_version, f"Failed for message: {message}")
    
    def test_progress_extraction(self):
        """测试进度提取"""
        test_cases = [
            ('Download progress: 45%', 45.0),
            ('Progress 50 / 100', 50.0),
            ('Completed 75.5%', 75.5),
            ('No progress info', None),
        ]
        
        for message, expected_progress in test_cases:
            progress = self.normalizer._extract_progress(message)
            self.assertEqual(progress, expected_progress, f"Failed for message: {message}")
    
    def test_error_code_extraction(self):
        """测试错误码提取"""
        test_cases = [
            ('Error code: NET_TIMEOUT', 'NET_TIMEOUT'),
            ('err: DISK_FULL', 'DISK_FULL'),
            ('Failed with [ERR_INVALID_SIGNATURE]', 'ERR_INVALID_SIGNATURE'),
            ('No error code', None),
        ]
        
        for message, expected_code in test_cases:
            code = self.normalizer._extract_error_code(message)
            self.assertEqual(code, expected_code, f"Failed for message: {message}")
    
    def test_batch_normalization(self):
        """测试批量标准化"""
        parsed_events = [
            {
                'source_type': 'android',
                'timestamp': datetime(2024, 1, 1, 10, 0, 0),
                'module': 'FotaService',
                'level': 'INFO',
                'message': 'FOTA init started',
                'raw': 'raw log 1',
            },
            {
                'source_type': 'android',
                'timestamp': datetime(2024, 1, 1, 10, 1, 0),
                'module': 'HeartbeatService',
                'level': 'DEBUG',
                'message': 'DEBUG: heartbeat tick',  # 噪音
                'raw': 'raw log 2',
            },
            {
                'source_type': 'android',
                'timestamp': datetime(2024, 1, 1, 10, 2, 0),
                'module': 'FotaDownload',
                'level': 'INFO',
                'message': 'Download progress: 50%',
                'raw': 'raw log 3',
            },
        ]
        
        time_alignment_result = {
            'offsets': {
                'android': {
                    'offset_seconds': 0.0,
                    'confidence': 0.95
                }
            }
        }
        
        normalized_events = self.normalizer.normalize_batch(
            parsed_events=parsed_events,
            case_id='CASE001',
            file_id='FILE001',
            time_alignment_result=time_alignment_result
        )
        
        # 应该过滤掉1个噪音事件
        self.assertEqual(len(normalized_events), 2)
        self.assertEqual(normalized_events[0].fota_stage, FotaStage.INIT)
        self.assertEqual(normalized_events[1].fota_progress, 50.0)
    
    def test_severity_determination(self):
        """测试严重程度判断"""
        test_cases = [
            ('FATAL', 'System crash detected', ErrorSeverity.CRITICAL),
            ('ERROR', 'Connection failed', ErrorSeverity.HIGH),
            ('WARN', 'Retry attempt 3', ErrorSeverity.MEDIUM),
            ('INFO', 'Process started', ErrorSeverity.INFO),
        ]
        
        for level, message, expected_severity in test_cases:
            severity = self.normalizer._determine_severity(level, message)
            self.assertEqual(severity, expected_severity)
    
    def test_category_classification(self):
        """测试事件分类"""
        test_cases = [
            ('FOTA update started', 'FotaService', EventCategory.FOTA_LIFECYCLE),
            ('Network connection established', 'NetworkManager', EventCategory.NETWORK),
            ('Disk space low', 'StorageManager', EventCategory.STORAGE),
            ('Battery level critical', 'PowerManager', EventCategory.POWER),
            ('System boot completed', 'SystemInit', EventCategory.SYSTEM_STATE),
            ('Unknown event', 'UnknownModule', EventCategory.UNKNOWN),
        ]
        
        for message, module, expected_category in test_cases:
            category = self.normalizer._classify_category(message, module)
            self.assertEqual(category, expected_category)


if __name__ == '__main__':
    unittest.main()
