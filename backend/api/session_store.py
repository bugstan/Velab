from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import ChatSession, ChatMessageRecord

router = APIRouter()


class SessionPayload(BaseModel):
    id: str
    title: str = "新会话"
    messages: list[dict[str, Any]] = Field(default_factory=list)
    createdAt: datetime
    updatedAt: datetime
    titleSource: Literal["default", "auto", "auto_optimized", "manual"] = "default"
    titleAutoOptimized: bool = False
    turnCount: int = 0


def _to_payload(session: ChatSession) -> SessionPayload:
    return SessionPayload(
        id=session.id,
        title=session.title,
        messages=[msg.payload for msg in sorted(session.messages, key=lambda m: m.seq)],
        createdAt=session.created_at,
        updatedAt=session.updated_at,
        titleSource=session.title_source,  # type: ignore[arg-type]
        titleAutoOptimized=session.title_auto_optimized,
        turnCount=session.turn_count,
    )


@router.get("", response_model=list[SessionPayload])
def list_sessions(db: Session = Depends(get_db)) -> list[SessionPayload]:
    sessions = (
        db.query(ChatSession)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    return [_to_payload(session) for session in sessions]


@router.get("/{session_id}", response_model=SessionPayload)
def get_session(session_id: str, db: Session = Depends(get_db)) -> SessionPayload:
    session = db.query(ChatSession).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _to_payload(session)


@router.put("/{session_id}", response_model=SessionPayload)
def upsert_session(
    session_id: str,
    payload: SessionPayload,
    db: Session = Depends(get_db),
) -> SessionPayload:
    if payload.id != session_id:
        raise HTTPException(status_code=400, detail="Session id mismatch")

    session = db.query(ChatSession).filter_by(id=session_id).first()
    if not session:
        session = ChatSession(
            id=session_id,
            created_at=payload.createdAt,
            updated_at=payload.updatedAt,
        )
        db.add(session)
        db.flush()

    session.title = payload.title.strip() or "新会话"
    session.title_source = payload.titleSource
    session.title_auto_optimized = payload.titleAutoOptimized
    session.turn_count = max(payload.turnCount, 0)
    if session.created_at is None:
        session.created_at = payload.createdAt
    session.updated_at = payload.updatedAt or datetime.utcnow()

    db.query(ChatMessageRecord).filter_by(session_id=session_id).delete()
    for seq, message in enumerate(payload.messages):
        db.add(
            ChatMessageRecord(
                session_id=session_id,
                seq=seq,
                payload=message,
            )
        )

    db.commit()
    db.refresh(session)
    return _to_payload(session)


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: str, db: Session = Depends(get_db)) -> None:
    session = db.query(ChatSession).filter_by(id=session_id).first()
    if not session:
        return None
    db.delete(session)
    db.commit()
    return None
