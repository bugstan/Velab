from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.llm import chat_completion

logger = logging.getLogger(__name__)

router = APIRouter()


class SessionTitleMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(default="", max_length=4000)


class SessionTitleRequest(BaseModel):
    messages: list[SessionTitleMessage] = Field(default_factory=list, min_length=1)
    mode: Literal["initial", "optimize"] = "initial"


class SessionTitleResponse(BaseModel):
    title: str


def _fallback_title(messages: list[SessionTitleMessage]) -> str:
    for msg in messages:
        if msg.role == "user" and msg.content.strip():
            text = " ".join(msg.content.strip().split())
            return text[:18] + ("..." if len(text) > 18 else "")
    return "新会话"


def _normalize_title(raw: str, fallback: str) -> str:
    text = (raw or "").strip().replace("\n", " ")
    if text.lower().startswith("title:"):
        text = text[6:].strip()
    if text.startswith("标题：") or text.startswith("标题:"):
        text = text.split("：", 1)[-1].split(":", 1)[-1].strip()
    text = text.strip("\"'` ")
    if not text:
        return fallback
    return text[:30]


@router.post("/title", response_model=SessionTitleResponse)
async def generate_session_title(payload: SessionTitleRequest) -> SessionTitleResponse:
    fallback = _fallback_title(payload.messages)
    transcript = "\n".join(
        f"{m.role}: {m.content[:400]}" for m in payload.messages if m.content.strip()
    )
    mode_hint = (
        "请根据第一轮对话生成简洁标题。"
        if payload.mode == "initial"
        else "请基于当前多轮对话优化标题，突出核心问题。"
    )
    prompt = (
        "你是聊天标题生成器。"
        "请输出一个中文标题，长度 12-18 字，避免敏感信息（VIN、手机号、车牌）。"
        "只返回标题本身，不要解释。"
    )
    try:
        msg = await chat_completion(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"{mode_hint}\n\n对话内容:\n{transcript}"},
            ],
            temperature=0.2,
            max_tokens=64,
            model="agent-model",
            stream=False,
        )
        title = _normalize_title(msg.content or "", fallback)
        return SessionTitleResponse(title=title)
    except Exception:
        logger.exception("session title generation failed")
        return SessionTitleResponse(title=fallback)
