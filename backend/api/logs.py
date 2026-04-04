"""
日志文件上传API

提供日志文件上传和管理接口
"""

import os
import hashlib
from datetime import datetime
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Case, RawLogFile
from models.log_file import ParseStatus
from api.schemas import (
    LogFileUploadResponse,
    LogFileResponse,
    LogFileListResponse,
    SuccessResponse
)
from config import settings

router = APIRouter()

# 日志文件存储根目录
STORAGE_ROOT = Path("/var/fota/logs")
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)


def _generate_file_id(case_id: str, filename: str, content: bytes) -> str:
    """
    生成唯一的文件ID
    
    使用案例ID、文件名和内容哈希生成唯一标识
    
    Args:
        case_id: 案例ID
        filename: 文件名
        content: 文件内容
        
    Returns:
        文件ID (格式: {case_id}_{timestamp}_{hash[:8]})
    """
    content_hash = hashlib.sha256(content).hexdigest()
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"{case_id}_{timestamp}_{content_hash[:8]}"


def _save_file(file_id: str, case_id: str, content: bytes) -> str:
    """
    保存文件到存储目录
    
    Args:
        file_id: 文件ID
        case_id: 案例ID
        content: 文件内容
        
    Returns:
        存储路径
    """
    # 创建案例目录
    case_dir = STORAGE_ROOT / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存文件
    file_path = case_dir / file_id
    file_path.write_bytes(content)
    
    return str(file_path)


@router.post("/upload", response_model=LogFileUploadResponse, status_code=201)
async def upload_log_file(
    case_id: str = Form(..., description="案例ID"),
    source_type: str = Form(..., description="日志源类型"),
    file: UploadFile = File(..., description="日志文件"),
    db: Session = Depends(get_db)
):
    """
    上传日志文件
    
    Args:
        case_id: 案例ID
        source_type: 日志源类型(android/kernel/fota/dlt/mcu/ibdu/vehicle_signal)
        file: 上传的文件
        db: 数据库会话
        
    Returns:
        上传成功的文件信息
        
    Raises:
        HTTPException: 案例不存在或文件类型不支持时返回错误
    """
    # 验证案例是否存在
    case = db.query(Case).filter_by(case_id=case_id).first()
    if not case:
        raise HTTPException(
            status_code=404,
            detail=f"Case '{case_id}' not found"
        )
    
    # 验证日志源类型
    valid_types = ["android", "kernel", "fota", "dlt", "mcu", "ibdu", "vehicle_signal"]
    if source_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source_type. Must be one of: {', '.join(valid_types)}"
        )
    
    # 读取文件内容
    content = await file.read()
    file_size = len(content)
    
    # 生成文件ID
    file_id = _generate_file_id(case_id, file.filename, content)
    
    # 保存文件
    storage_path = _save_file(file_id, case_id, content)
    
    # 创建数据库记录
    log_file = RawLogFile(
        case_id=case_id,
        file_id=file_id,
        original_filename=file.filename,
        file_size=file_size,
        source_type=source_type,
        storage_path=storage_path,
        parse_status=ParseStatus.PENDING.value
    )
    
    db.add(log_file)
    db.commit()
    db.refresh(log_file)
    
    return LogFileUploadResponse(
        file_id=log_file.file_id,
        case_id=log_file.case_id,
        original_filename=log_file.original_filename,
        file_size=log_file.file_size,
        source_type=log_file.source_type,
        storage_path=log_file.storage_path,
        parse_status=log_file.parse_status,
        uploaded_at=log_file.uploaded_at
    )


@router.get("/{file_id}", response_model=LogFileResponse)
def get_log_file(
    file_id: str,
    db: Session = Depends(get_db)
):
    """
    获取日志文件详情
    
    Args:
        file_id: 文件ID
        db: 数据库会话
        
    Returns:
        文件详情
        
    Raises:
        HTTPException: 文件不存在时返回404
    """
    log_file = db.query(RawLogFile).filter_by(file_id=file_id).first()
    if not log_file:
        raise HTTPException(
            status_code=404,
            detail=f"Log file '{file_id}' not found"
        )
    
    return log_file


@router.get("", response_model=LogFileListResponse)
def list_log_files(
    case_id: Optional[str] = Query(None, description="按案例ID筛选"),
    source_type: Optional[str] = Query(None, description="按日志源类型筛选"),
    parse_status: Optional[str] = Query(None, description="按解析状态筛选"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    db: Session = Depends(get_db)
):
    """
    获取日志文件列表
    
    Args:
        case_id: 案例ID筛选(可选)
        source_type: 日志源类型筛选(可选)
        parse_status: 解析状态筛选(可选)
        limit: 返回数量限制
        offset: 偏移量
        db: 数据库会话
        
    Returns:
        文件列表和总数
    """
    query = db.query(RawLogFile)
    
    # 应用筛选条件
    if case_id:
        query = query.filter(RawLogFile.case_id == case_id)
    if source_type:
        query = query.filter(RawLogFile.source_type == source_type)
    if parse_status:
        query = query.filter(RawLogFile.parse_status == parse_status)
    
    # 获取总数
    total = query.count()
    
    # 分页查询
    files = query.order_by(RawLogFile.uploaded_at.desc()).offset(offset).limit(limit).all()
    
    return LogFileListResponse(total=total, items=files)


@router.delete("/{file_id}", response_model=SuccessResponse)
def delete_log_file(
    file_id: str,
    db: Session = Depends(get_db)
):
    """
    删除日志文件
    
    删除文件会同时删除存储的物理文件和数据库记录
    
    Args:
        file_id: 文件ID
        db: 数据库会话
        
    Returns:
        成功响应
        
    Raises:
        HTTPException: 文件不存在时返回404
    """
    log_file = db.query(RawLogFile).filter_by(file_id=file_id).first()
    if not log_file:
        raise HTTPException(
            status_code=404,
            detail=f"Log file '{file_id}' not found"
        )
    
    # 删除物理文件
    try:
        file_path = Path(log_file.storage_path)
        if file_path.exists():
            file_path.unlink()
    except Exception as e:
        # 记录错误但继续删除数据库记录
        print(f"Failed to delete physical file: {e}")
    
    # 删除数据库记录
    db.delete(log_file)
    db.commit()
    
    return SuccessResponse(
        success=True,
        message=f"Log file '{file_id}' deleted successfully"
    )
