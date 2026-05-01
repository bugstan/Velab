"""
后端测试公共 fixtures（PostgreSQL 业务侧：cases / confirmed_diagnosis）。

日志解析 / bundle 摄取相关测试已迁出至 ``backend/log_pipeline/tests/``，独立 conftest。
"""

import os
from datetime import datetime
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from database import get_db
from models import Case
from models.base import Base


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture(scope="function")
def test_db() -> Generator[Session, None, None]:
    connect_args = {}
    if TEST_DATABASE_URL.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args=connect_args,
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(test_db: Session) -> TestClient:
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_case(test_db: Session) -> Case:
    case = Case(
        case_id="test_case_001",
        vin="TEST1234567890123",
        vehicle_model="Model X",
        issue_description="Test issue",
        status="active",
        created_at=datetime.utcnow(),
    )
    test_db.add(case)
    test_db.commit()
    test_db.refresh(case)
    return case
