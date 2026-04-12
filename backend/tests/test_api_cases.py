"""
Cases API 单元测试
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import Case


class TestCasesAPI:
    """Cases API测试类"""
    
    def test_create_case(self, client: TestClient, test_db: Session):
        """测试创建案例"""
        response = client.post(
            "/api/cases",
            json={
                "case_id": "new_case_001",
                "vin": "VIN1234567890123",
                "vehicle_model": "Model Y",
                "issue_description": "Engine warning light"
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["case_id"] == "new_case_001"
        assert data["vin"] == "VIN1234567890123"
        assert data["status"] == "active"
        
        # 验证数据库中存在
        case = test_db.query(Case).filter_by(case_id="new_case_001").first()
        assert case is not None
        assert case.vehicle_model == "Model Y"
    
    def test_create_case_duplicate(self, client: TestClient, sample_case: Case):
        """测试创建重复案例"""
        response = client.post(
            "/api/cases",
            json={
                "case_id": sample_case.case_id,
                "vin": "VIN9999999999999",
                "vehicle_model": "Model Z",
                "issue_description": "Test"
            }
        )
        
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]
    
    def test_get_case(self, client: TestClient, sample_case: Case):
        """测试获取案例详情"""
        response = client.get(f"/api/cases/{sample_case.case_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["case_id"] == sample_case.case_id
        assert data["vin"] == sample_case.vin
        assert data["vehicle_model"] == sample_case.vehicle_model
    
    def test_get_case_not_found(self, client: TestClient):
        """测试获取不存在的案例"""
        response = client.get("/api/cases/nonexistent_case")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
    
    def test_list_cases(self, client: TestClient, sample_case: Case):
        """测试列出案例"""
        response = client.get("/api/cases")
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1
        assert len(data["items"]) >= 1
        
        # 验证第一个案例
        first_case = data["items"][0]
        assert "case_id" in first_case
        assert "vin" in first_case
    
    def test_list_cases_with_filters(self, client: TestClient, sample_case: Case):
        """测试带过滤条件的案例列表"""
        response = client.get(
            "/api/cases",
            params={
                "vin": sample_case.vin,
                "status": "active"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        
        # 验证过滤结果
        for case in data["items"]:
            assert case["vin"] == sample_case.vin
            assert case["status"] == "active"
    
    def test_list_cases_pagination(self, client: TestClient, test_db: Session):
        """测试分页"""
        # 创建多个案例
        for i in range(15):
            case = Case(
                case_id=f"page_case_{i:03d}",
                vin=f"VIN{i:017d}",
                vehicle_model="Model X",
                issue_description=f"Issue {i}"
            )
            test_db.add(case)
        test_db.commit()
        
        # 测试第一页
        response = client.get("/api/cases", params={"skip": 0, "limit": 10})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["total"] >= 15
        
        # 测试第二页
        response = client.get("/api/cases", params={"skip": 10, "limit": 10})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 5
    
    def test_delete_case(self, client: TestClient, sample_case: Case, test_db: Session):
        """测试删除案例"""
        response = client.delete(f"/api/cases/{sample_case.case_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        
        # 验证数据库中已删除
        case = test_db.query(Case).filter_by(case_id=sample_case.case_id).first()
        assert case is None
    
    def test_delete_case_not_found(self, client: TestClient):
        """测试删除不存在的案例"""
        response = client.delete("/api/cases/nonexistent_case")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
