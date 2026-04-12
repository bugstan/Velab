"""
Events API 单元测试
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import Case, DiagnosisEvent


class TestEventsAPI:
    """Events API测试类"""
    
    def test_query_events(
        self, 
        client: TestClient, 
        sample_case: Case, 
        sample_events
    ):
        """测试查询事件"""
        response = client.post(
            "/api/events/query",
            json={
                "case_id": sample_case.case_id,
                "skip": 0,
                "limit": 10
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] == 5
        assert len(data["items"]) == 5
        
        # 验证事件结构
        first_event = data["items"][0]
        assert "id" in first_event
        assert "message" in first_event
        assert "level" in first_event
    
    def test_query_events_with_filters(
        self, 
        client: TestClient, 
        sample_case: Case, 
        sample_events
    ):
        """测试带过滤条件的事件查询"""
        response = client.post(
            "/api/events/query",
            json={
                "case_id": sample_case.case_id,
                "source_type": "android",
                "level": "INFO",
                "skip": 0,
                "limit": 10
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        
        # 验证过滤结果
        for event in data["items"]:
            assert event["source_type"] == "android"
            assert event["level"] == "INFO"
    
    def test_query_events_with_time_range(
        self, 
        client: TestClient, 
        sample_case: Case, 
        sample_events
    ):
        """测试带时间范围的事件查询"""
        response = client.post(
            "/api/events/query",
            json={
                "case_id": sample_case.case_id,
                "start_time": "2024-01-01T10:00:00",
                "end_time": "2024-01-01T10:00:02",
                "skip": 0,
                "limit": 10
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        # 应该返回前3个事件（秒数0,1,2）
        assert data["total"] == 3
    
    def test_query_events_with_keyword(
        self, 
        client: TestClient, 
        sample_case: Case, 
        sample_events
    ):
        """测试关键词搜索"""
        response = client.post(
            "/api/events/query",
            json={
                "case_id": sample_case.case_id,
                "keyword": "event 2",
                "skip": 0,
                "limit": 10
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        
        # 验证搜索结果
        for event in data["items"]:
            assert "event 2" in event["message"].lower()
    
    def test_query_events_pagination(
        self, 
        client: TestClient, 
        sample_case: Case, 
        sample_events
    ):
        """测试分页"""
        # 第一页
        response = client.post(
            "/api/events/query",
            json={
                "case_id": sample_case.case_id,
                "skip": 0,
                "limit": 2
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5
        
        # 第二页
        response = client.post(
            "/api/events/query",
            json={
                "case_id": sample_case.case_id,
                "skip": 2,
                "limit": 2
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
    
    def test_get_event_by_id(
        self, 
        client: TestClient, 
        sample_events
    ):
        """测试获取单个事件"""
        event_id = sample_events[0].id
        response = client.get(f"/api/events/{event_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == event_id
        assert "message" in data
        assert "level" in data
    
    def test_get_event_not_found(self, client: TestClient):
        """测试获取不存在的事件"""
        response = client.get("/api/events/999999")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
    
    def test_get_case_summary(
        self, 
        client: TestClient, 
        sample_case: Case, 
        sample_events
    ):
        """测试获取案例统计摘要"""
        response = client.get(f"/api/events/case/{sample_case.case_id}/summary")
        
        assert response.status_code == 200
        data = response.json()
        assert data["case_id"] == sample_case.case_id
        assert data["total_events"] == 5
        assert "by_source" in data
        assert "by_level" in data
        assert "by_type" in data
        assert "time_range" in data
    
    def test_get_case_summary_not_found(self, client: TestClient):
        """测试获取不存在案例的摘要"""
        response = client.get("/api/events/case/nonexistent_case/summary")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
    
    def test_export_events_json(
        self, 
        client: TestClient, 
        sample_case: Case, 
        sample_events
    ):
        """测试导出事件为JSON"""
        response = client.post(
            "/api/events/export",
            json={
                "case_id": sample_case.case_id,
                "format": "json"
            }
        )
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        
        # 验证响应是流式的
        content = response.content
        assert len(content) > 0
    
    def test_export_events_csv(
        self, 
        client: TestClient, 
        sample_case: Case, 
        sample_events
    ):
        """测试导出事件为CSV"""
        response = client.post(
            "/api/events/export",
            json={
                "case_id": sample_case.case_id,
                "format": "csv"
            }
        )
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        
        # 验证CSV内容
        content = response.text
        assert "id" in content  # CSV header
        assert "message" in content
        assert len(content.split("\n")) > 1  # 至少有header和数据行
    
    def test_export_events_with_filters(
        self, 
        client: TestClient, 
        sample_case: Case, 
        sample_events
    ):
        """测试带过滤条件的导出"""
        response = client.post(
            "/api/events/export",
            json={
                "case_id": sample_case.case_id,
                "format": "json",
                "source_type": "android",
                "level": "info"
            }
        )
        
        assert response.status_code == 200
    
    def test_export_events_case_not_found(self, client: TestClient):
        """测试导出不存在案例的事件"""
        response = client.post(
            "/api/events/export",
            json={
                "case_id": "nonexistent_case",
                "format": "json"
            }
        )
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
