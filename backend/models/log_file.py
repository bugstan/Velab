"""
原始日志文件模型

对应数据库表: raw_log_files
"""

from datetime import datetime
from typing import Optional
from enum import Enum

from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship

from .base import Base


class ParseStatus(str, Enum):
    """解析状态枚举"""
    PENDING = "PENDING"
    PARSING = "PARSING"
    PARSED = "PARSED"
    FAILED = "FAILED"


class RawLogFile(Base):
    """
    原始日志文件元数据模型
    
    存储上传的日志文件信息,包括存储路径、解析状态等
    """
    __tablename__ = 'raw_log_files'
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 外键
    case_id = Column(String(100), ForeignKey('cases.case_id', ondelete='CASCADE'), nullable=False, index=True)
    
    # 文件信息
    file_id = Column(String(128), unique=True, nullable=False, index=True)
    original_filename = Column(String(500), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    mime_type = Column(String(100))
    source_type = Column(String(32), nullable=False, index=True)  # android/kernel/fota/dlt/mcu/ibdu/vehicle_signal
    storage_path = Column(Text, nullable=False)  # MinIO对象存储路径
    
    # 上传时间
    upload_time = Column(DateTime, default=datetime.utcnow)
    
    # 解析状态
    parse_status = Column(String(32), default=ParseStatus.PENDING.value, index=True)
    parse_started_at = Column(DateTime)
    parse_completed_at = Column(DateTime)
    parse_error = Column(Text)
    
    # 元数据(JSONB)
    metadata = Column(JSON, default=dict)
    
    # 创建时间
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    case = relationship('Case', back_populates='log_files')
    events = relationship('DiagnosisEvent', back_populates='log_file', cascade='all, delete-orphan')
    
    def __repr__(self) -> str:
        return f"<RawLogFile(file_id='{self.file_id}', filename='{self.original_filename}', status='{self.parse_status}')>"
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            'id': self.id,
            'case_id': self.case_id,
            'file_id': self.file_id,
            'original_filename': self.original_filename,
            'file_size': self.file_size,
            'mime_type': self.mime_type,
            'source_type': self.source_type,
            'storage_path': self.storage_path,
            'upload_time': self.upload_time.isoformat() if self.upload_time else None,
            'parse_status': self.parse_status,
            'parse_started_at': self.parse_started_at.isoformat() if self.parse_started_at else None,
            'parse_completed_at': self.parse_completed_at.isoformat() if self.parse_completed_at else None,
            'parse_error': self.parse_error,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
