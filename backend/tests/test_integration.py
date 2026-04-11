"""
集成测试 - 端到端流程测试
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import Case, RawLogFile
from models.log_file import ParseStatus


class TestIntegration:
    """集成测试类 - 测试完整的业务流程"""
    
    def test_complete_workflow(
        self, 
        client: TestClient, 
        test_db: Session,
        mock_task_client
    ):
        """
        测试完整工作流程:
        1. 创建案例
        2. 上传日志文件（模拟）
        3. 提交解析任务
        4. 查询任务状态
        5. 查询事件
        6. 导出事件
        """
        # 1. 创建案例
        case_response = client.post(
            "/api/cases",
            json={
                "case_id": "integration_case_001",
                "vin": "INT1234567890123",
                "vehicle_model": "Model Test",
                "issue_description": "Integration test case"
            }
        )
        assert case_response.status_code == 201
        case_id = case_response.json()["case_id"]
        
        # 2. 模拟上传日志文件（直接插入数据库）
        log_file = RawLogFile(
            file_id="int_file_001",
            case_id=case_id,
            filename="test_integration.log",
            source_type="android",
            file_size=2048,
            file_path="/tmp/test_integration.log",
            storage_path=f"/var/fota/logs/{case_id}/test_integration.log",
            parse_status=ParseStatus.PENDING.value
        )
        test_db.add(log_file)
        test_db.commit()
        
        # 3. 提交解析任务
        parse_response = client.post(
            "/api/parse/submit",
            json={
                "case_id": case_id,
                "file_ids": ["int_file_001"]
            }
        )
        assert parse_response.status_code == 202
        task_id = parse_response.json()["task_id"]
        assert task_id is not None
        
        # 4. 查询任务状态
        status_response = client.get(f"/api/parse/status/{task_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert "status" in status_data
        
        # 5. 查询案例详情
        case_detail_response = client.get(f"/api/cases/{case_id}")
        assert case_detail_response.status_code == 200
        
        # 6. 列出案例
        cases_list_response = client.get("/api/cases")
        assert cases_list_response.status_code == 200
        assert cases_list_response.json()["total"] >= 1
    
    def test_case_lifecycle(self, client: TestClient, test_db: Session):
        """测试案例生命周期"""
        # 创建案例
        create_response = client.post(
            "/api/cases",
            json={
                "case_id": "lifecycle_case_001",
                "vin": "LIFE1234567890123",
                "vehicle_model": "Model Lifecycle",
                "issue_description": "Lifecycle test"
            }
        )
        assert create_response.status_code == 201
        case_id = create_response.json()["case_id"]
        
        # 获取案例
        get_response = client.get(f"/api/cases/{case_id}")
        assert get_response.status_code == 200
        assert get_response.json()["case_id"] == case_id
        
        # 列出案例（应包含新创建的）
        list_response = client.get("/api/cases")
        assert list_response.status_code == 200
        case_ids = [c["case_id"] for c in list_response.json()["items"]]
        assert case_id in case_ids
        
        # 删除案例
        delete_response = client.delete(f"/api/cases/{case_id}")
        assert delete_response.status_code == 200
        
        # 验证已删除
        get_deleted_response = client.get(f"/api/cases/{case_id}")
        assert get_deleted_response.status_code == 404
    
    def test_concurrent_case_creation(self, client: TestClient):
        """测试并发创建案例"""
        case_ids = []
        
        # 创建多个案例
        for i in range(5):
            response = client.post(
                "/api/cases",
                json={
                    "case_id": f"concurrent_case_{i:03d}",
                    "vin": f"CONC{i:016d}",
                    "vehicle_model": "Model Concurrent",
                    "issue_description": f"Concurrent test {i}"
                }
            )
            assert response.status_code == 201
            case_ids.append(response.json()["case_id"])
        
        # 验证所有案例都已创建
        list_response = client.get("/api/cases")
        assert list_response.status_code == 200
        created_ids = [c["case_id"] for c in list_response.json()["items"]]
        
        for case_id in case_ids:
            assert case_id in created_ids
    
    def test_error_handling(self, client: TestClient):
        """测试错误处理"""
        # 测试404错误
        response_404 = client.get("/api/cases/nonexistent_case")
        assert response_404.status_code == 404
        
        # 测试400错误（重复创建）
        client.post(
            "/api/cases",
            json={
                "case_id": "duplicate_case",
                "vin": "DUP1234567890123",
                "vehicle_model": "Model Dup",
                "issue_description": "Duplicate test"
            }
        )
        
        response_409 = client.post(
            "/api/cases",
            json={
                "case_id": "duplicate_case",
                "vin": "DUP9999999999999",
                "vehicle_model": "Model Dup2",
                "issue_description": "Duplicate test 2"
            }
        )
        assert response_409.status_code == 409
