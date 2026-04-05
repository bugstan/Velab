"""
数据库操作测试

测试ORM模型、连接池和批量操作功能
"""

import unittest
from datetime import datetime, timedelta
from pathlib import Path
import sys

# 添加backend目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import DatabaseManager, db_manager
from db_operations import BatchOperations
from models.case import Case
from models.log_file import RawLogFile, ParseStatus
from models.event import DiagnosisEvent
from models.diagnosis import ConfirmedDiagnosis


class TestDatabaseModels(unittest.TestCase):
    """测试ORM模型"""
    
    @classmethod
    def setUpClass(cls):
        """初始化测试数据库"""
        # 使用测试数据库URL
        import os
        os.environ['DB_HOST'] = 'localhost'
        os.environ['DB_PORT'] = '5432'
        os.environ['DB_NAME'] = 'fota_test'
        os.environ['DB_USER'] = 'postgres'
        os.environ['DB_PASSWORD'] = 'postgres'
        
        # 初始化数据库管理器
        db_manager.initialize(pool_size=2, echo=False)
        
        # 创建表
        db_manager.create_tables()
    
    @classmethod
    def tearDownClass(cls):
        """清理测试数据库"""
        db_manager.close()
    
    def setUp(self):
        """每个测试前清理数据"""
        with db_manager.get_session() as session:
            # 清空所有表
            session.query(ConfirmedDiagnosis).delete()
            session.query(DiagnosisEvent).delete()
            session.query(RawLogFile).delete()
            session.query(Case).delete()
            session.commit()
    
    def test_create_case(self):
        """测试创建案件"""
        with db_manager.get_session() as session:
            case = Case(
                case_id='TEST001',
                vin='TESTVIN1234567890',
                vehicle_model='Model X',
                status='OPEN',
                metadata={'test': True}
            )
            session.add(case)
            session.commit()
            
            # 查询验证
            result = session.query(Case).filter_by(case_id='TEST001').first()
            self.assertIsNotNone(result)
            self.assertEqual(result.vin, 'TESTVIN1234567890')
            self.assertEqual(result.vehicle_model, 'Model X')
            self.assertEqual(result.metadata['test'], True)
    
    def test_create_log_file(self):
        """测试创建日志文件"""
        with db_manager.get_session() as session:
            # 先创建案件
            case = Case(case_id='TEST002', vin='VIN002')
            session.add(case)
            session.commit()
            
            # 创建日志文件
            log_file = RawLogFile(
                case_id='TEST002',
                file_id='FILE001',
                original_filename='android.log',
                file_size=1024000,
                mime_type='text/plain',
                source_type='android',
                storage_path='/minio/logs/android.log',
                parse_status=ParseStatus.PENDING.value
            )
            session.add(log_file)
            session.commit()
            
            # 查询验证
            result = session.query(RawLogFile).filter_by(file_id='FILE001').first()
            self.assertIsNotNone(result)
            self.assertEqual(result.original_filename, 'android.log')
            self.assertEqual(result.source_type, 'android')
            self.assertEqual(result.parse_status, ParseStatus.PENDING.value)
    
    def test_create_diagnosis_event(self):
        """测试创建诊断事件"""
        with db_manager.get_session() as session:
            # 创建案件和日志文件
            case = Case(case_id='TEST003', vin='VIN003')
            session.add(case)
            session.commit()
            
            log_file = RawLogFile(
                case_id='TEST003',
                file_id='FILE002',
                original_filename='fota.log',
                file_size=2048000,
                source_type='fota',
                storage_path='/minio/logs/fota.log'
            )
            session.add(log_file)
            session.commit()
            
            # 创建诊断事件
            event = DiagnosisEvent(
                case_id='TEST003',
                file_id='FILE002',
                source_type='fota',
                original_ts=datetime.utcnow(),
                normalized_ts=datetime.utcnow(),
                event_type='FOTA_STAGE',
                module='FotaDownload',
                level='INFO',
                message='Download started',
                raw_line_number=100,
                parsed_fields={'stage': 'download', 'progress': 0}
            )
            session.add(event)
            session.commit()
            
            # 查询验证
            result = session.query(DiagnosisEvent).filter_by(case_id='TEST003').first()
            self.assertIsNotNone(result)
            self.assertEqual(result.event_type, 'FOTA_STAGE')
            self.assertEqual(result.module, 'FotaDownload')
            self.assertEqual(result.parsed_fields['stage'], 'download')
    
    def test_cascade_delete(self):
        """测试级联删除"""
        with db_manager.get_session() as session:
            # 创建完整的数据链
            case = Case(case_id='TEST004', vin='VIN004')
            session.add(case)
            session.commit()
            
            log_file = RawLogFile(
                case_id='TEST004',
                file_id='FILE003',
                original_filename='test.log',
                file_size=1000,
                source_type='android',
                storage_path='/test.log'
            )
            session.add(log_file)
            session.commit()
            
            event = DiagnosisEvent(
                case_id='TEST004',
                file_id='FILE003',
                source_type='android',
                normalized_ts=datetime.utcnow(),
                message='Test event'
            )
            session.add(event)
            session.commit()
            
            # 删除案件,应该级联删除日志文件和事件
            session.delete(case)
            session.commit()
            
            # 验证级联删除
            self.assertIsNone(session.query(RawLogFile).filter_by(file_id='FILE003').first())
            self.assertIsNone(session.query(DiagnosisEvent).filter_by(case_id='TEST004').first())


class TestBatchOperations(unittest.TestCase):
    """测试批量操作"""
    
    @classmethod
    def setUpClass(cls):
        """初始化测试数据库"""
        import os
        os.environ['DB_HOST'] = 'localhost'
        os.environ['DB_PORT'] = '5432'
        os.environ['DB_NAME'] = 'fota_test'
        os.environ['DB_USER'] = 'postgres'
        os.environ['DB_PASSWORD'] = 'postgres'
        
        db_manager.initialize(pool_size=2, echo=False)
        db_manager.create_tables()
    
    @classmethod
    def tearDownClass(cls):
        """清理测试数据库"""
        db_manager.close()
    
    def setUp(self):
        """每个测试前准备数据"""
        with db_manager.get_session() as session:
            # 清空数据
            session.query(DiagnosisEvent).delete()
            session.query(RawLogFile).delete()
            session.query(Case).delete()
            session.commit()
            
            # 创建测试案件和日志文件
            case = Case(case_id='BATCH001', vin='VINBATCH001')
            session.add(case)
            session.commit()
            
            log_file = RawLogFile(
                case_id='BATCH001',
                file_id='BATCHFILE001',
                original_filename='batch_test.log',
                file_size=10000000,
                source_type='android',
                storage_path='/batch_test.log'
            )
            session.add(log_file)
            session.commit()
    
    def test_bulk_insert_events(self):
        """测试批量插入事件"""
        # 准备1000条测试事件
        events = []
        base_time = datetime.utcnow()
        
        for i in range(1000):
            events.append({
                'case_id': 'BATCH001',
                'file_id': 'BATCHFILE001',
                'source_type': 'android',
                'original_ts': base_time + timedelta(seconds=i),
                'normalized_ts': base_time + timedelta(seconds=i),
                'event_type': 'LOG',
                'module': 'TestModule',
                'level': 'INFO',
                'message': f'Test message {i}',
                'raw_line_number': i + 1,
            })
        
        # 批量插入
        with db_manager.get_session() as session:
            count = BatchOperations.bulk_insert_events(session, events, batch_size=100)
            
            self.assertEqual(count, 1000)
            
            # 验证插入结果
            total = session.query(DiagnosisEvent).filter_by(case_id='BATCH001').count()
            self.assertEqual(total, 1000)
    
    def test_update_file_parse_status(self):
        """测试更新文件解析状态"""
        with db_manager.get_session() as session:
            # 更新为PARSING状态
            BatchOperations.update_file_parse_status(
                session,
                'BATCHFILE001',
                ParseStatus.PARSING
            )
            
            log_file = session.query(RawLogFile).filter_by(file_id='BATCHFILE001').first()
            self.assertEqual(log_file.parse_status, ParseStatus.PARSING.value)
            self.assertIsNotNone(log_file.parse_started_at)
            
            # 更新为PARSED状态
            BatchOperations.update_file_parse_status(
                session,
                'BATCHFILE001',
                ParseStatus.PARSED
            )
            
            log_file = session.query(RawLogFile).filter_by(file_id='BATCHFILE001').first()
            self.assertEqual(log_file.parse_status, ParseStatus.PARSED.value)
            self.assertIsNotNone(log_file.parse_completed_at)
    
    def test_get_events_by_case(self):
        """测试查询案件事件"""
        # 先插入一些测试事件
        events = []
        base_time = datetime.utcnow()
        
        for i in range(100):
            events.append({
                'case_id': 'BATCH001',
                'file_id': 'BATCHFILE001',
                'source_type': 'android',
                'normalized_ts': base_time + timedelta(seconds=i),
                'event_type': 'ERROR' if i % 10 == 0 else 'LOG',
                'module': 'ModuleA' if i % 2 == 0 else 'ModuleB',
                'level': 'ERROR' if i % 10 == 0 else 'INFO',
                'message': f'Message {i}',
                'raw_line_number': i + 1,
            })
        
        with db_manager.get_session() as session:
            BatchOperations.bulk_insert_events(session, events)
            
            # 查询所有事件
            all_events = BatchOperations.get_events_by_case(session, 'BATCH001', limit=200)
            self.assertEqual(len(all_events), 100)
            
            # 查询ERROR类型事件
            error_events = BatchOperations.get_events_by_case(
                session,
                'BATCH001',
                event_types=['ERROR']
            )
            self.assertEqual(len(error_events), 10)
            
            # 查询特定模块事件
            module_a_events = BatchOperations.get_events_by_case(
                session,
                'BATCH001',
                modules=['ModuleA']
            )
            self.assertEqual(len(module_a_events), 50)


class TestConnectionPool(unittest.TestCase):
    """测试连接池"""
    
    def test_pool_initialization(self):
        """测试连接池初始化"""
        manager = DatabaseManager()
        manager.initialize(pool_size=5, max_overflow=10)
        
        status = manager.get_pool_status()
        self.assertEqual(status['size'], 5)
        
        manager.close()
    
    def test_multiple_sessions(self):
        """测试多个会话"""
        manager = DatabaseManager()
        manager.initialize(pool_size=3)
        
        # 创建多个会话
        sessions = []
        for i in range(5):
            with manager.get_session() as session:
                sessions.append(session)
                # 简单查询
                result = session.execute("SELECT 1").scalar()
                self.assertEqual(result, 1)
        
        manager.close()


if __name__ == '__main__':
    # 运行测试
    print("=" * 60)
    print("数据库操作测试")
    print("=" * 60)
    print("\n注意: 需要先创建测试数据库 'fota_test'")
    print("CREATE DATABASE fota_test;\n")
    
    unittest.main(verbosity=2)
