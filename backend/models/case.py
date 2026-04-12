"""
案件模型

对应数据库表: cases
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.orm import relationship

from .base import Base


class Case(Base):
    """
    案件元数据模型
    
    存储FOTA诊断案件的基本信息,包括VIN码、车型等
    """
    __tablename__ = 'cases'
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 业务字段
    case_id = Column(String(100), unique=True, nullable=False, index=True)
    vin = Column(String(17), index=True)
    vehicle_model = Column(String(100))
    issue_description = Column(String(500))
    status = Column(String(50), default="active")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 元数据(JSONB) - 使用meta_data避免与SQLAlchemy保留字冲突
    meta_data = Column('metadata', JSON, default=dict)
    
    # 关系
    log_files = relationship('RawLogFile', back_populates='case', cascade='all, delete-orphan')
    events = relationship('DiagnosisEvent', back_populates='case', cascade='all, delete-orphan')
    diagnoses = relationship('ConfirmedDiagnosis', back_populates='case', cascade='all, delete-orphan')
    
    def __repr__(self) -> str:
        return f"<Case(case_id='{self.case_id}', vin='{self.vin}', status='{self.status}')>"
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            'id': self.id,
            'case_id': self.case_id,
            'vin': self.vin,
            'vehicle_model': self.vehicle_model,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'metadata': self.meta_data,
        }
