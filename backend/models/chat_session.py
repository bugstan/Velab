"""
聊天会话持久化模型

对应数据库表:
- chat_sessions
- chat_messages
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .base import Base


class ChatSession(Base):
    """聊天会话主表"""

    __tablename__ = "chat_sessions"

    id = Column(String(100), primary_key=True)
    title = Column(String(255), nullable=False, default="新会话")
    title_source = Column(String(32), nullable=False, default="default")
    title_auto_optimized = Column(Boolean, nullable=False, default=False)
    turn_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        index=True,
    )

    messages = relationship(
        "ChatMessageRecord",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessageRecord.seq.asc()",
    )


class ChatMessageRecord(Base):
    """聊天消息表，payload 原样保存前端消息对象"""

    __tablename__ = "chat_messages"
    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_chat_messages_session_id_seq"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        String(100),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seq = Column(Integer, nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    session = relationship("ChatSession", back_populates="messages")
