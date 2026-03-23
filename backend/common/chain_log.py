"""
调用链日志：统一时间戳与字段格式，配合 contextvars 传递 trace_id。

环境变量：
  LOG_LEVEL=DEBUG|INFO|WARNING  默认 DEBUG（便于看全链路）
"""

from __future__ import annotations

import contextvars
import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

# ---------------------------------------------------------------------------
# 格式定义（供 setup_logging 与文档约定）
# ---------------------------------------------------------------------------


class ChainLogFormat:
    """控制台行格式：行首为 logging 时间，消息体内仍带 ts= 便于跨系统对齐。"""

    LINE = "%(asctime)s.%(msecs)03d %(levelname)s [%(name)s] %(message)s"
    DATEFMT = "%Y-%m-%dT%H:%M:%S"


def setup_logging(
    level: int | None = None,
    *,
    stream: Any = None,
    force_if_no_handlers: bool = True,
) -> None:
    """
    初始化 root logging。若已有 handler（如 uvicorn），只下调 root level。
    """
    if level is None:
        level = getattr(logging, (os.environ.get("LOG_LEVEL") or "DEBUG").upper(), logging.DEBUG)

    root = logging.getLogger()
    stream = stream or sys.stderr

    if not root.handlers:
        if force_if_no_handlers:
            logging.basicConfig(
                level=level,
                format=ChainLogFormat.LINE,
                datefmt=ChainLogFormat.DATEFMT,
                stream=stream,
            )
    else:
        root.setLevel(min(root.level, level) if root.level else level)


# ---------------------------------------------------------------------------
# Trace（单次 /chat SSE 请求一条）
# ---------------------------------------------------------------------------

_trace_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("chain_trace_id", default="")


def new_trace_id() -> str:
    return uuid.uuid4().hex[:12]


def bind_trace_id(tid: str) -> contextvars.Token:
    return _trace_ctx.set(tid)


def reset_trace_id(token: contextvars.Token) -> None:
    _trace_ctx.reset(token)


def current_trace_id() -> str:
    t = _trace_ctx.get()
    return t if t else "-"


def iso_ts_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _fmt_extra(kwargs: dict[str, Any]) -> str:
    if not kwargs:
        return ""
    parts = []
    for k, v in kwargs.items():
        if v is None:
            continue
        s = str(v)
        if len(s) > 200:
            s = s[:200] + "…"
        parts.append(f"{k}={s}")
    return (" " + " ".join(parts)) if parts else ""


def chain_log(
    logger: logging.Logger,
    level: int,
    *,
    step: str,
    event: str,
    msg: str = "",
    elapsed_ms: float | None = None,
    **kwargs: Any,
) -> None:
    """统一 [CHAIN] 前缀 + trace + step + event + 行内 ts + 可选耗时。"""
    tid = current_trace_id()
    bits = [
        "[CHAIN]",
        f"trace={tid}",
        f"step={step}",
        f"event={event}",
        f"ts={iso_ts_utc()}",
    ]
    if elapsed_ms is not None:
        bits.append(f"elapsed_ms={elapsed_ms:.1f}")
    if msg:
        bits.append(msg)
    extra = _fmt_extra(kwargs)
    if extra:
        bits.append(extra.strip())
    logger.log(level, " ".join(bits))


def chain_debug(logger: logging.Logger, **kw: Any) -> None:
    chain_log(logger, logging.DEBUG, **kw)


def chain_info(logger: logging.Logger, **kw: Any) -> None:
    chain_log(logger, logging.INFO, **kw)


@asynccontextmanager
async def async_step_timer(
    logger: logging.Logger,
    step: str,
    **start_kw: Any,
) -> Iterator[None]:
    t0 = time.perf_counter()
    chain_debug(logger, step=step, event="START", **start_kw)
    try:
        yield
    finally:
        chain_debug(
            logger,
            step=step,
            event="END",
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )


@contextmanager
def sync_step_timer(
    logger: logging.Logger,
    step: str,
    **start_kw: Any,
) -> Iterator[None]:
    t0 = time.perf_counter()
    chain_debug(logger, step=step, event="START", **start_kw)
    try:
        yield
    finally:
        chain_debug(
            logger,
            step=step,
            event="END",
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )
