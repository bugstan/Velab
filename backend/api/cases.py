"""
案例管理API

提供案例的CRUD操作接口
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Case
from api.schemas import (
    CaseCreate,
    CaseResponse,
    CaseListResponse,
    SuccessResponse,
    ErrorResponse
)

router = APIRouter()


@router.post("", response_model=CaseResponse, status_code=201)
def create_case(
    case_data: CaseCreate,
    db: Session = Depends(get_db)
):
    """
    创建新案例
    
    Args:
        case_data: 案例创建数据
        db: 数据库会话
        
    Returns:
        创建的案例信息
        
    Raises:
        HTTPException: 案例ID已存在时返回409
    """
    # 检查案例ID是否已存在
    existing = db.query(Case).filter_by(case_id=case_data.case_id).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Case with ID '{case_data.case_id}' already exists"
        )
    
    # 创建新案例
    case = Case(
        case_id=case_data.case_id,
        vin=case_data.vin,
        vehicle_model=case_data.vehicle_model,
        issue_description=case_data.issue_description,
        status="active",
        meta_data=case_data.metadata
    )
    
    db.add(case)
    db.commit()
    db.refresh(case)
    
    return case


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(
    case_id: str,
    db: Session = Depends(get_db)
):
    """
    获取案例详情
    
    Args:
        case_id: 案例ID
        db: 数据库会话
        
    Returns:
        案例详情
        
    Raises:
        HTTPException: 案例不存在时返回404
    """
    case = db.query(Case).filter_by(case_id=case_id).first()
    if not case:
        raise HTTPException(
            status_code=404,
            detail=f"Case '{case_id}' not found"
        )
    
    return case


@router.get("", response_model=CaseListResponse)
def list_cases(
    vin: Optional[str] = Query(None, description="按VIN筛选"),
    vehicle_model: Optional[str] = Query(None, description="按车型筛选"),
    status: Optional[str] = Query(None, description="按状态筛选"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    db: Session = Depends(get_db)
):
    """
    获取案例列表
    
    Args:
        vin: VIN码筛选(可选)
        vehicle_model: 车型筛选(可选)
        status: 状态筛选(可选)
        limit: 返回数量限制
        offset: 偏移量
        db: 数据库会话
        
    Returns:
        案例列表和总数
    """
    query = db.query(Case)
    
    # 应用筛选条件
    if vin:
        query = query.filter(Case.vin == vin)
    if vehicle_model:
        query = query.filter(Case.vehicle_model == vehicle_model)
    if status:
        query = query.filter(Case.status == status)
    
    # 获取总数
    total = query.count()
    
    # 分页查询
    cases = query.order_by(Case.created_at.desc()).offset(offset).limit(limit).all()
    
    return CaseListResponse(total=total, items=cases)


@router.delete("/{case_id}", response_model=SuccessResponse)
def delete_case(
    case_id: str,
    db: Session = Depends(get_db)
):
    """
    删除案例
    
    删除案例会级联删除关联的日志文件和事件
    
    Args:
        case_id: 案例ID
        db: 数据库会话
        
    Returns:
        成功响应
        
    Raises:
        HTTPException: 案例不存在时返回404
    """
    case = db.query(Case).filter_by(case_id=case_id).first()
    if not case:
        raise HTTPException(
            status_code=404,
            detail=f"Case '{case_id}' not found"
        )
    
    db.delete(case)
    db.commit()
    
    return SuccessResponse(
        success=True,
        message=f"Case '{case_id}' deleted successfully"
    )
