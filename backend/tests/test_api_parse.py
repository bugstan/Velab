"""
Parse API 单元测试
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import Case, RawLogFile
from models.log_file import ParseStatus


class TestParseAPI:
    """Parse API测试类"""
    
    def test_submit_parse_task(
        self, 
        client: TestClient, 
        sample_case: Case, 
        sample_log_file: RawLogFile,
        mock_task_client
    ):
        """测试提交解析任务"""
        response = client.post(
            "/api/parse/submit",
            json={
                "case_id": sample_case.case_id,
                "file_ids": [sample_log_file.file_id]
            }
        )
        
        assert response.status_code == 202
        data = response.json()
        assert "task_id" in data
        assert data["case_id"] == sample_case.case_id
        assert data["status"] == "pending"
        assert data["total_files"] == 1
    
    def test_submit_parse_task_case_not_found(self, client: TestClient, mock_task_client):
        """测试提交解析任务 - 案例不存在"""
        response = client.post(
            "/api/parse/submit",
            json={
                "case_id": "nonexistent_case",
                "file_ids": ["file_001"]
            }
        )
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
    
    def test_submit_parse_task_no_files(
        self, 
        client: TestClient, 
        sample_case: Case,
        mock_task_client
    ):
        """测试提交解析任务 - 无文件可解析"""
        response = client.post(
            "/api/parse/submit",
            json={
                "case_id": sample_case.case_id,
                "file_ids": []
            }
        )
        
        assert response.status_code == 400
        assert "No files to parse" in response.json()["detail"]
    
    def test_submit_parse_task_with_time_window(
        self, 
        client: TestClient, 
        sample_case: Case, 
        sample_log_file: RawLogFile,
        mock_task_client
    ):
        """测试提交解析任务 - 带时间窗口"""
        response = client.post(
            "/api/parse/submit",
            json={
                "case_id": sample_case.case_id,
                "file_ids": [sample_log_file.file_id],
                "time_window_start": "2024-01-01T00:00:00",
                "time_window_end": "2024-01-01T23:59:59",
                "max_lines_per_file": 10000
            }
        )
        
        assert response.status_code == 202
        data = response.json()
        assert data["total_files"] == 1
    
    def test_get_parse_task_status(self, client: TestClient, mock_task_client):
        """测试查询解析任务状态"""
        task_id = "test_task_12345"
        response = client.get(f"/api/parse/status/{task_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert data["status"] == "completed"
        assert "result" in data
    
    def test_align_case_time(
        self, 
        client: TestClient, 
        sample_case: Case, 
        sample_events
    ):
        """测试时间对齐"""
        response = client.post(f"/api/parse/align-time/{sample_case.case_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "aligned_sources" in data["data"]
        assert "total_events" in data["data"]
    
    def test_align_case_time_case_not_found(self, client: TestClient):
        """测试时间对齐 - 案例不存在"""
        response = client.post("/api/parse/align-time/nonexistent_case")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
    
    def test_align_case_time_no_events(self, client: TestClient, sample_case: Case):
        """测试时间对齐 - 无事件"""
        response = client.post(f"/api/parse/align-time/{sample_case.case_id}")
        
        assert response.status_code == 400
        assert "No events found" in response.json()["detail"]
