"""
敏感信息脱敏模块 — VIN 码、手机号、车牌号。

来源: src/llm/client.py 中的 SENSITIVE_PATTERNS + redact_sensitive_info + @sensitive_redactor
"""

from __future__ import annotations

import functools
import inspect
import logging
import re
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)

# ── 脱敏正则 ──────────────────────────────────────────────────────
SENSITIVE_PATTERNS: dict[str, str] = {
    "VIN": r"[A-HJ-NPR-Z0-9]{17}",
    "PHONE": r"1[3-9]\d{9}",
    "PLATE": (
        r"[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁使领]"
        r"[A-Z][A-HJ-NP-Z0-9]{4,5}[A-HJ-NP-Z0-9挂学警港澳试超]"
    ),
}

# 预编译正则以提升性能
_COMPILED_PATTERNS: list[tuple[str, re.Pattern]] = [
    (label, re.compile(pattern)) for label, pattern in SENSITIVE_PATTERNS.items()
]


def redact_sensitive_info(text: str) -> str:
    """对文本中的 VIN、手机号、车牌号执行脱敏替换。"""
    for label, compiled in _COMPILED_PATTERNS:
        text = compiled.sub(f"[REDACTED_{label}]", text)
    return text


def _extract_messages(func, args: tuple, kwargs: dict) -> list[dict] | None:
    """
    从位置参数或关键字参数中提取 ``messages`` 参数。

    兼容 ``chat_completion(messages, ...)`` 和
    ``chat_completion(messages=messages, ...)`` 两种调用方式。
    """
    # 优先从 kwargs 取
    if "messages" in kwargs:
        return kwargs["messages"]
    # 从位置参数中按函数签名定位
    try:
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())
        if "messages" in params:
            idx = params.index("messages")
            if idx < len(args) and isinstance(args[idx], list):
                return args[idx]
    except (ValueError, TypeError):
        pass
    # 退化：取第一个 list[dict] 类型的位置参数
    for arg in args:
        if isinstance(arg, list) and arg and isinstance(arg[0], dict):
            return arg
    return None


def sensitive_redactor(func):
    """
    异步脱敏装饰器：

    - 拦截 ``messages`` 参数（无论位置/关键字传入），对内容做脱敏后写入 DEBUG 日志
    - 拦截非流式返回值，对内容做脱敏后写入 DEBUG 日志
    - 流式 (AsyncGenerator) 返回值透传，不干预迭代
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        # ── 输入脱敏日志 ──
        messages = _extract_messages(func, args, kwargs)
        if messages:
            sanitized_messages = [
                {
                    "role": msg.get("role"),
                    "content": redact_sensitive_info(str(msg.get("content", ""))),
                }
                for msg in messages
            ]
            logger.debug("LLM Input (redacted): %s", sanitized_messages)

        try:
            result = await func(*args, **kwargs)

            # 流式输出不做后处理
            if isinstance(result, AsyncGenerator):
                return result

            # ── 输出脱敏日志 ──
            logger.debug("LLM Output (redacted): %s", redact_sensitive_info(str(result)))
            return result
        except Exception as e:
            logger.error("LLM Call Error: %s", str(e))
            raise

    return wrapper
