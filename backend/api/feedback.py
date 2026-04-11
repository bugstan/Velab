"""
已确认诊断缓存 + 反馈闭环 API

工程师对诊断结果的确认/拒绝/部分确认，
为后续相似案例检索和置信度校准提供数据基础。

对应数据库表：confirmed_diagnosis

作者：FOTA 诊断平台团队
创建时间：2026-04-06
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from models import ConfirmedDiagnosis, Case

router = APIRouter()


# ── Schemas ──

class DiagnosisFeedbackCreate(BaseModel):
    """提交诊断反馈"""
    case_id: str = Field(..., description="案件 ID")
    root_cause: str = Field(..., description="根因描述")
    confidence: float = Field(..., ge=0.0, le=1.0, description="置信度")
    recommendations: List[str] = Field(default_factory=list, description="建议列表")
    confirmed_by: str = Field(..., description="确认工程师 ID 或邮箱")
    confirmation_status: str = Field(
        ..., description="确认状态: CONFIRMED / REJECTED / PARTIAL"
    )
    engineer_notes: Optional[str] = Field(None, description="工程师备注")
    evidence_log_ids: List[int] = Field(default_factory=list, description="关联日志事件 ID")
    evidence_jira_ids: List[str] = Field(default_factory=list, description="关联 Jira Issue ID")
    evidence_doc_ids: List[str] = Field(default_factory=list, description="关联文档 chunk ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="其他元数据")


class DiagnosisFeedbackResponse(BaseModel):
    """诊断反馈响应"""
    id: int
    case_id: str
    root_cause: str
    confidence: float
    confirmation_status: str
    confirmed_by: Optional[str]
    confirmed_at: datetime
    engineer_notes: Optional[str]
    created_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict, validation_alias="meta_data")

    class Config:
        from_attributes = True


class FeedbackStats(BaseModel):
    """反馈统计"""
    total: int
    confirmed: int
    rejected: int
    partial: int
    avg_confidence: float


# ── Endpoints ──

@router.post("", response_model=DiagnosisFeedbackResponse, status_code=201)
def submit_feedback(
    data: DiagnosisFeedbackCreate,
    db: Session = Depends(get_db),
):
    """
    提交诊断反馈

    工程师确认/拒绝/部分确认诊断结论
    """
    # 检查案件存在
    case = db.query(Case).filter_by(case_id=data.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {data.case_id} not found")

    if data.confirmation_status not in ("CONFIRMED", "REJECTED", "PARTIAL"):
        raise HTTPException(
            status_code=400,
            detail="confirmation_status must be CONFIRMED, REJECTED, or PARTIAL",
        )

    feedback = ConfirmedDiagnosis(
        case_id=data.case_id,
        root_cause=data.root_cause,
        confidence=data.confidence,
        recommendations=data.recommendations,
        confirmed_by=data.confirmed_by,
        confirmed_at=datetime.utcnow(),
        confirmation_status=data.confirmation_status,
        engineer_notes=data.engineer_notes,
        evidence_log_ids=data.evidence_log_ids,
        evidence_jira_ids=data.evidence_jira_ids,
        evidence_doc_ids=data.evidence_doc_ids,
        meta_data=data.metadata,
    )

    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    return feedback


@router.get("/case/{case_id}", response_model=List[DiagnosisFeedbackResponse])
def get_case_feedback(
    case_id: str,
    db: Session = Depends(get_db),
):
    """获取案件的所有诊断反馈"""
    feedbacks = (
        db.query(ConfirmedDiagnosis)
        .filter_by(case_id=case_id)
        .order_by(ConfirmedDiagnosis.confirmed_at.desc())
        .all()
    )
    return feedbacks


@router.get("/{feedback_id}", response_model=DiagnosisFeedbackResponse)
def get_feedback(
    feedback_id: int,
    db: Session = Depends(get_db),
):
    """获取单个反馈详情"""
    feedback = db.query(ConfirmedDiagnosis).filter_by(id=feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return feedback


@router.get("", response_model=List[DiagnosisFeedbackResponse])
def list_feedback(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """
    列出所有诊断反馈

    可按确认状态过滤
    """
    query = db.query(ConfirmedDiagnosis)
    if status:
        query = query.filter_by(confirmation_status=status)
    return query.order_by(ConfirmedDiagnosis.confirmed_at.desc()).offset(offset).limit(limit).all()


@router.get("/stats/summary", response_model=FeedbackStats)
def get_feedback_stats(db: Session = Depends(get_db)):
    """获取反馈统计摘要"""
    total = db.query(func.count(ConfirmedDiagnosis.id)).scalar() or 0
    confirmed = (
        db.query(func.count(ConfirmedDiagnosis.id))
        .filter_by(confirmation_status="CONFIRMED")
        .scalar()
        or 0
    )
    rejected = (
        db.query(func.count(ConfirmedDiagnosis.id))
        .filter_by(confirmation_status="REJECTED")
        .scalar()
        or 0
    )
    partial = (
        db.query(func.count(ConfirmedDiagnosis.id))
        .filter_by(confirmation_status="PARTIAL")
        .scalar()
        or 0
    )
    avg_conf = (
        db.query(func.avg(ConfirmedDiagnosis.confidence)).scalar() or 0.0
    )

    return FeedbackStats(
        total=total,
        confirmed=confirmed,
        rejected=rejected,
        partial=partial,
        avg_confidence=round(float(avg_conf), 3),
    )
