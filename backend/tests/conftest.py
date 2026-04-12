"""
API测试配置和Fixtures

提供测试数据库、测试客户端等共享fixtures
"""

import pytest
from datetime import datetime
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from main import app
from database import get_db, db_manager
from models.base import Base
from models import Case, RawLogFile, DiagnosisEvent
from models.log_file import ParseStatus


# 测试数据库URL（优先从环境变量读取，默认为内存SQLite）
import os
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")



@pytest.fixture(scope="function")
def test_db() -> Generator[Session, None, None]:
    """
    创建测试数据库会话
    
    每个测试函数使用独立的内存数据库
    """
    # 根据数据库类型配置 connect_args
    connect_args = {}
    if TEST_DATABASE_URL.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        
    # 创建测试引擎
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args=connect_args,
        poolclass=StaticPool,
    )

    
    # 创建所有表
    Base.metadata.create_all(bind=engine)
    
    # 创建会话
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(test_db: Session) -> TestClient:
    """
    创建测试客户端
    
    覆盖依赖注入，使用测试数据库
    """
    def override_get_db():
        try:
            yield test_db
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


@pytest.fixture
def sample_case(test_db: Session) -> Case:
    """创建示例案例"""
    case = Case(
        case_id="test_case_001",
        vin="TEST1234567890123",
        vehicle_model="Model X",
        issue_description="Test issue",
        status="active",
        created_at=datetime.utcnow()
    )
    test_db.add(case)
    test_db.commit()
    test_db.refresh(case)
    return case


@pytest.fixture
def sample_log_file(test_db: Session, sample_case: Case) -> RawLogFile:
    """创建示例日志文件"""
    log_file = RawLogFile(
        file_id="test_file_001",
        case_id=sample_case.case_id,
        original_filename="test.log",
        source_type="android",
        file_size=1024,
        storage_path="/var/fota/logs/test_case_001/test.log",
        parse_status=ParseStatus.PENDING.value,
        upload_time=datetime.utcnow()
    )
    test_db.add(log_file)
    test_db.commit()
    test_db.refresh(log_file)
    return log_file


@pytest.fixture
def sample_events(test_db: Session, sample_case: Case, sample_log_file: RawLogFile) -> list[DiagnosisEvent]:
    """创建示例诊断事件"""
    events = []
    base_time = datetime(2024, 1, 1, 10, 0, 0)
    
    for i in range(5):
        event = DiagnosisEvent(
            case_id=sample_case.case_id,
            file_id=sample_log_file.file_id,
            source_type="android",
            original_ts=base_time.replace(second=i),
            normalized_ts=base_time.replace(second=i),
            event_type="LOG",
            level="INFO",
            module="system",
            message=f"Test event {i}",
            raw_snippet=f"Test line {i}",
            raw_line_number=i + 1,
            parsed_fields={"test": True}
        )
        events.append(event)
        test_db.add(event)
    
    test_db.commit()
    for event in events:
        test_db.refresh(event)
    
    return events


@pytest.fixture(autouse=True)
def mock_task_client(monkeypatch):
    """Mock任务客户端（避免依赖Redis）"""
    class MockTaskClient:
        async def initialize(self):
            pass
        
        async def close(self):
            pass
        
        async def submit_parse_task(self, *args, **kwargs):
            return "mock_task_id_12345"
        
        async def get_task_status(self, task_id: str):
            return {
                "task_id": task_id,
                "status": "completed",
                "result": {
                    "case_id": "test_case_001",
                    "total_files": 1,
                    "parsed_files": 1,
                    "failed_files": 0,
                    "total_events": 100,
                    "status": "completed"
                }
            }
    
    async def mock_get_task_client():
        return MockTaskClient()
    
    # Mock任务客户端
    from tasks import client as task_client_module
    from api import parse as api_parse_module
    monkeypatch.setattr(task_client_module, "get_task_client", mock_get_task_client)
    monkeypatch.setattr(api_parse_module, "get_task_client", mock_get_task_client)
