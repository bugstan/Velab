"""
API 请求/响应 schema 定义。

日志解析、文件、事件相关的旧 schema 已移除，对应能力由 log_pipeline 提供（/api/bundles/...）。
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field


# ========== 案例相关 ==========

class CaseCreate(BaseModel):
    case_id: str = Field(..., description="案例ID", max_length=100)
    vin: Optional[str] = Field(None, description="车辆VIN码", max_length=17)
    vehicle_model: Optional[str] = Field(None, description="车型", max_length=100)
    issue_description: Optional[str] = Field(None, description="问题描述")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="元数据")


class CaseResponse(BaseModel):
    id: int
    case_id: str
    vin: Optional[str]
    vehicle_model: Optional[str]
    issue_description: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="meta_data")

    class Config:
        from_attributes = True


class CaseListResponse(BaseModel):
    total: int
    items: List[CaseResponse]


# ========== 通用响应 ==========

class SuccessResponse(BaseModel):
    success: bool = True
    message: str
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    detail: Optional[str] = None
