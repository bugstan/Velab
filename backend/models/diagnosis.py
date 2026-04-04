"""
已确认诊断模型

对应数据库表: confirmed_diagnosis
"""

from datetime import datetime
from typing import Optional, List

from sqlalchemy import Column, Integer, String, DateTime, Text, Float, ForeignKey, JSON, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY

from .base import Base


class ConfirmedDiagnosis(Base):
    """
    已确认诊断模型
    
    存储工程师确认的诊断结果,用于反馈闭环和长期记忆
    """
    __tablename__ = 'confirmed_diagnosis'
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 外键
    case_id = Column(String(100), ForeignKey('cases.case_id', ondelete='CASCADE'), nullable=False, index=True)
    
    # 诊断结果
    root_cause = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    recommendations = Column(PG_ARRAY(Text))
    
    # 工程师确认信息
    confirmed_by = Column(String(100))  # 工程师ID或邮箱
    confirmed_at = Column(DateTime, nullable=False, index=True)
    confirmation_status = Column(String(20), nullable=False, index=True)  # CONFIRMED/REJECTED/PARTIAL
    engineer_notes = Column(Text)
    
    # 关联证据
    evidence_log_ids = Column(PG_ARRAY(Integer))  # 关联的 diagnosis_events.id
    evidence_jira_ids = Column(PG_ARRAY(String(200)))  # 关联的 Jira Issue ID
    evidence_doc_ids = Column(PG_ARRAY(String(200)))  # 关联的文档 chunk ID
    
    # 向量化（用于相似案例检索）
    # diagnosis_embedding = Column(Vector(1536))  # 需要pgvector扩展
    
    # 元数据
    meta_data = Column('metadata', JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    case = relationship('Case', back_populates='diagnoses')
    
    def __repr__(self) -> str:
        return f"<ConfirmedDiagnosis(id={self.id}, case_id='{self.case_id}', status='{self.confirmation_status}')>"
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            'id': self.id,
            'case_id': self.case_id,
            'root_cause': self.root_cause,
            'confidence': self.confidence,
            'recommendations': self.recommendations,
            'confirmed_by': self.confirmed_by,
            'confirmed_at': self.confirmed_at.isoformat() if self.confirmed_at else None,
            'confirmation_status': self.confirmation_status,
            'engineer_notes': self.engineer_notes,
            'evidence_log_ids': self.evidence_log_ids,
            'evidence_jira_ids': self.evidence_jira_ids,
            'evidence_doc_ids': self.evidence_doc_ids,
            'metadata': self.meta_data,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
