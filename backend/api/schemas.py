"""
API数据模型定义

使用Pydantic定义请求和响应的数据结构
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

from pydantic import BaseModel, Field


# ========== 枚举类型 ==========

class ParseStatus(str, Enum):
    """解析状态"""
    PENDING = "PENDING"
    PARSING = "PARSING"
    PARSED = "PARSED"
    FAILED = "FAILED"


class SourceType(str, Enum):
    """日志源类型"""
    ANDROID = "android"
    FOTA_HMI = "fota_hmi"
    DLT = "dlt"
    MCU = "mcu"
    IBDU = "ibdu"


class ExportFormat(str, Enum):
    """导出格式"""
    JSON = "json"
    CSV = "csv"


# ========== 案例相关 ==========

class CaseCreate(BaseModel):
    """创建案例请求"""
    case_id: str = Field(..., description="案例ID", max_length=100)
    vin: Optional[str] = Field(None, description="车辆VIN码", max_length=17)
    vehicle_model: Optional[str] = Field(None, description="车型", max_length=100)
    issue_description: Optional[str] = Field(None, description="问题描述")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="元数据")


class CaseResponse(BaseModel):
    """案例响应"""
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
    """案例列表响应"""
    total: int
    items: List[CaseResponse]


# ========== 日志文件相关 ==========

class LogFileUploadResponse(BaseModel):
    """日志文件上传响应"""
    file_id: str = Field(..., description="文件ID")
    case_id: str = Field(..., description="案例ID")
    original_filename: str = Field(..., description="原始文件名")
    file_size: int = Field(..., description="文件大小(字节)")
    source_type: str = Field(..., description="日志源类型")
    storage_path: str = Field(..., description="存储路径")
    parse_status: str = Field(..., description="解析状态")
    uploaded_at: datetime = Field(..., description="上传时间")


class LogFileResponse(BaseModel):
    """日志文件响应"""
    id: int
    file_id: str
    case_id: str
    original_filename: str
    file_size: int
    source_type: str
    storage_path: str
    parse_status: str
    error_message: Optional[str] = Field(default=None, validation_alias="parse_error")
    uploaded_at: datetime = Field(validation_alias="upload_time")
    updated_at: datetime = Field(validation_alias="created_at")
    metadata: Dict[str, Any] = Field(default_factory=dict, validation_alias="meta_data")
    
    class Config:
        from_attributes = True


class LogFileListResponse(BaseModel):
    """日志文件列表响应"""
    total: int
    items: List[LogFileResponse]


# ========== 解析任务相关 ==========

class ParseTaskSubmit(BaseModel):
    """提交解析任务请求"""
    case_id: str = Field(..., description="案例ID")
    file_ids: Optional[List[str]] = Field(None, description="文件ID列表(为空则解析该案例所有文件)")
    time_window_start: Optional[datetime] = Field(None, description="时间窗口起始(快速通道)")
    time_window_end: Optional[datetime] = Field(None, description="时间窗口结束(快速通道)")
    max_lines_per_file: Optional[int] = Field(None, description="每个文件最大解析行数")


class ParseTaskResponse(BaseModel):
    """解析任务响应"""
    task_id: str = Field(..., description="任务ID")
    case_id: str = Field(..., description="案例ID")
    status: str = Field(..., description="任务状态")
    total_files: int = Field(..., description="总文件数")
    parsed_files: int = Field(..., description="已解析文件数")
    failed_files: int = Field(..., description="失败文件数")
    total_events: int = Field(..., description="总事件数")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    error_message: Optional[str] = Field(None, description="错误信息")


# ========== 事件相关 ==========

class EventQuery(BaseModel):
    """事件查询请求"""
    case_id: str = Field(..., description="案例ID")
    source_type: Optional[str] = Field(None, description="日志源类型")
    event_type: Optional[str] = Field(None, description="事件类型")
    module: Optional[str] = Field(None, description="模块名")
    level: Optional[str] = Field(None, description="日志级别")
    start_time: Optional[datetime] = Field(None, description="起始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    keyword: Optional[str] = Field(None, description="关键词搜索")
    limit: int = Field(1000, description="返回数量限制", ge=1, le=10000)
    offset: int = Field(0, description="偏移量", ge=0)


class EventResponse(BaseModel):
    """事件响应"""
    id: int
    case_id: str
    file_id: str
    source_type: str
    original_ts: Optional[datetime]
    normalized_ts: Optional[datetime]
    clock_confidence: float
    event_type: str
    module: Optional[str]
    level: str
    message: str
    parsed_fields: Dict[str, Any]
    raw_line_number: Optional[int]
    raw_snippet: Optional[str]
    
    class Config:
        from_attributes = True


class EventListResponse(BaseModel):
    """事件列表响应"""
    total: int
    items: List[EventResponse]
    query: EventQuery


class EventExportRequest(BaseModel):
    """事件导出请求"""
    case_id: str = Field(..., description="案例ID")
    format: ExportFormat = Field(ExportFormat.JSON, description="导出格式")
    source_type: Optional[str] = Field(None, description="日志源类型")
    start_time: Optional[datetime] = Field(None, description="起始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")


# ========== 通用响应 ==========

class SuccessResponse(BaseModel):
    """成功响应"""
    success: bool = True
    message: str
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    """错误响应"""
    success: bool = False
    error: str
    detail: Optional[str] = None
