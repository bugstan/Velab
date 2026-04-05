"""
诊断事件模型

对应数据库表: diagnosis_events
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, BigInteger, Integer, String, DateTime, Text, Float, ForeignKey, JSON, Index
from sqlalchemy.orm import relationship

from .base import Base


class DiagnosisEvent(Base):
    """
    诊断事件模型
    
    存储解析后的结构化事件,包括时间对齐、事件分类等信息
    """
    __tablename__ = 'diagnosis_events'
    
    # 主键
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    
    # 外键
    case_id = Column(String(100), ForeignKey('cases.case_id', ondelete='CASCADE'), nullable=False, index=True)
    file_id = Column(String(128), ForeignKey('raw_log_files.file_id', ondelete='CASCADE'), nullable=False)
    
    # 来源类型
    source_type = Column(String(32), nullable=False)
    
    # 时间戳字段
    original_ts = Column(DateTime)  # 原始日志中的时间戳
    normalized_ts = Column(DateTime, index=True)  # 时间对齐后的标准化时间戳
    clock_confidence = Column(Float, default=1.0)  # 时间对齐置信度 (0.0-1.0)
    
    # 事件内容
    event_type = Column(String(100), index=True)  # ERROR/WARNING/INFO/STATE_CHANGE/FOTA_STAGE
    module = Column(String(100), index=True)
    level = Column(String(20))  # ERROR/WARN/INFO/DEBUG
    message = Column(Text, nullable=False)
    
    # 原始日志回溯
    raw_line_number = Column(Integer)
    raw_snippet = Column(Text)  # 原始日志片段（前后各3行）
    
    # 结构化解析字段（因日志类型而异）
    parsed_fields = Column(JSON, default=dict)
    
    # 元数据
    parser_name = Column(String(64))
    parser_version = Column(String(32), default='1.0.0')
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    case = relationship('Case', back_populates='events')
    log_file = relationship('RawLogFile', back_populates='events')
    
    # 复合索引
    __table_args__ = (
        Index('ix_diagnosis_events_case_time', 'case_id', 'normalized_ts'),
        Index('ix_diagnosis_events_case_module', 'case_id', 'module'),
    )
    
    def __repr__(self) -> str:
        return f"<DiagnosisEvent(id={self.id}, type='{self.event_type}', module='{self.module}', level='{self.level}')>"
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            'id': self.id,
            'case_id': self.case_id,
            'file_id': self.file_id,
            'source_type': self.source_type,
            'original_ts': self.original_ts.isoformat() if self.original_ts else None,
            'normalized_ts': self.normalized_ts.isoformat() if self.normalized_ts else None,
            'clock_confidence': self.clock_confidence,
            'event_type': self.event_type,
            'module': self.module,
            'level': self.level,
            'message': self.message,
            'raw_line_number': self.raw_line_number,
            'raw_snippet': self.raw_snippet,
            'parsed_fields': self.parsed_fields,
            'parser_name': self.parser_name,
            'parser_version': self.parser_version,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
