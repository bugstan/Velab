"""
LLM service — 多供应商统一客户端 (LiteLLM 中转 / 直连)。

完整实现 src/llm/client.py 全部功能：
  - DeploymentMode A/B 客户端自动切换
  - 敏感信息脱敏（VIN / 手机号 / 车牌号）
  - chat_completion（阻塞/流式聚合 + tool calling）
  - chat_completion_stream（真流式 SSE delta 输出）
  - get_embeddings（向量嵌入）
  - parse_tool_calls
  - 全链路 chain_log 调用链日志
"""

from __future__ import annotations

import json
import logging
import time
from types import SimpleNamespace
from typing import Any, AsyncIterator, List

from openai import AsyncOpenAI

from common.chain_log import chain_debug
from common.redaction import redact_sensitive_info, sensitive_redactor
from config import settings, DeploymentMode

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────────
# Client singleton
# ────────────────────────────────────────────────────────────────────

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    """根据 DeploymentMode 懒加载 AsyncOpenAI 客户端。"""
    global _client
    if _client is None:
        if settings.DEPLOYMENT_MODE == DeploymentMode.SCENARIO_A:
            # 场景 A: 统一使用 OpenAI 协议访问 LiteLLM 网关
            _client = AsyncOpenAI(
                base_url=settings.LLM_BASE_URL,
                api_key=settings.LLM_API_KEY,
            )
        else:
            # 场景 B: 直连供应商 (OpenAI 兼容)
            _client = AsyncOpenAI(
                api_key=settings.LLM_API_KEY,
            )
    return _client


# ────────────────────────────────────────────────────────────────────
# chat_completion (阻塞 + 流式聚合)
# ────────────────────────────────────────────────────────────────────


@sensitive_redactor
async def chat_completion(
    messages: list[dict],
    tools: list[dict] | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    *,
    model: str = "agent-model",
    stream: bool = False,
) -> Any:
    """
    统一对话接口 — 对应 src/llm/client.py 的 LLMClient.chat_completions()。

    - model 默认 ``agent-model``（LiteLLM 网关虚拟模型名）
    - 场景 B 直连时，需传入实际模型名（如 ``gpt-4o``）
    - stream=True 时自动聚合为完整 message 返回（供 tool calling 使用）
    """
    t0 = time.perf_counter()
    chain_debug(
        logger,
        step="llm.chat_completion",
        event="START",
        model=model,
        tools=bool(tools),
        msg_count=len(messages),
        max_tokens=max_tokens,
        stream_mode=stream,
        deployment_mode=settings.DEPLOYMENT_MODE.value,
    )
    client = get_client()

    try:
        if stream:
            msg = await _accumulate_streamed_completion(
                client=client,
                model=model,
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                t0=t0,
            )
        else:
            kwargs: dict[str, Any] = dict(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            resp = await client.chat.completions.create(**kwargs)
            msg = resp.choices[0].message
    except Exception:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        chain_debug(
            logger,
            step="llm.chat_completion",
            event="ERROR",
            elapsed_ms=elapsed_ms,
            stream_mode=stream,
        )
        logger.exception("[LLM] chat_completion failed")
        raise

    elapsed_ms = (time.perf_counter() - t0) * 1000
    n_tools = len(msg.tool_calls or [])
    content_len = len(msg.content or "")
    chain_debug(
        logger,
        step="llm.chat_completion",
        event="END",
        elapsed_ms=elapsed_ms,
        tool_calls=n_tools,
        content_chars=content_len,
        stream_mode=stream,
    )
    return msg


# ────────────────────────────────────────────────────────────────────
# 流式聚合 (内部)
# ────────────────────────────────────────────────────────────────────


async def _accumulate_streamed_completion(
    *,
    client: AsyncOpenAI,
    model: str,
    messages: list[dict],
    tools: list[dict] | None,
    temperature: float,
    max_tokens: int,
    t0: float,
) -> Any:
    """流式拉取后聚合为与阻塞式相同的 message 形态（供 parse_tool_calls 使用）。"""
    kwargs: dict[str, Any] = dict(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    stream_iter = await client.chat.completions.create(**kwargs)
    t_headers = (time.perf_counter() - t0) * 1000
    chain_debug(
        logger,
        step="llm.chat_completion",
        event="STREAM_OPEN",
        model=model,
        since_start_ms=round(t_headers, 1),
        stream_mode=True,
    )

    content_parts: list[str] = []
    tc_buf: dict[int, dict[str, str]] = {}
    chunk_idx = 0
    first_content_ms: float | None = None

    async for chunk in stream_iter:
        chunk_idx += 1
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            if first_content_ms is None:
                first_content_ms = (time.perf_counter() - t0) * 1000
                chain_debug(
                    logger,
                    step="llm.chat_completion",
                    event="FIRST_CONTENT",
                    ttft_ms=round(first_content_ms, 1),
                    raw_chunks=chunk_idx,
                    stream_mode=True,
                )
            content_parts.append(delta.content)
        if delta.tool_calls:
            for ptc in delta.tool_calls:
                i = ptc.index
                if i not in tc_buf:
                    tc_buf[i] = {"id": "", "name": "", "arguments": ""}
                if ptc.id:
                    tc_buf[i]["id"] = ptc.id
                if ptc.function:
                    if ptc.function.name:
                        tc_buf[i]["name"] = ptc.function.name
                    if ptc.function.arguments:
                        tc_buf[i]["arguments"] += ptc.function.arguments

    full_content = "".join(content_parts) if content_parts else None
    tool_calls_ns: list[Any] = []
    for i in sorted(tc_buf.keys()):
        b = tc_buf[i]
        tool_calls_ns.append(
            SimpleNamespace(
                id=b["id"] or f"call_{i}",
                function=SimpleNamespace(
                    name=b["name"],
                    arguments=b["arguments"],
                ),
            )
        )

    return SimpleNamespace(
        content=full_content,
        tool_calls=tool_calls_ns if tool_calls_ns else None,
    )


# ────────────────────────────────────────────────────────────────────
# chat_completion_stream (真流式 — yield text deltas)
# ────────────────────────────────────────────────────────────────────


async def chat_completion_stream(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    model: str = "agent-model",
) -> AsyncIterator[str]:
    """真流式输出 — yield 每个 text delta，用于 SSE 推送。"""
    t0 = time.perf_counter()
    client = get_client()

    chain_debug(
        logger,
        step="llm.chat_completion_stream",
        event="START",
        model=model,
        msg_count=len(messages),
        max_tokens=max_tokens,
        deployment_mode=settings.DEPLOYMENT_MODE.value,
    )

    # 输入脱敏日志
    for msg in messages:
        logger.debug(
            "LLM Stream Input [%s]: %s",
            msg.get("role"),
            redact_sensitive_info(str(msg.get("content", ""))[:200]),
        )

    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
    except Exception:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        chain_debug(
            logger,
            step="llm.chat_completion_stream",
            event="ERROR",
            msg="before_iterate",
            elapsed_ms=elapsed_ms,
        )
        logger.exception("[LLM] chat_completion_stream create failed")
        raise

    t_http_ms = (time.perf_counter() - t0) * 1000
    chain_debug(
        logger,
        step="llm.chat_completion_stream",
        event="STREAM_OPEN",
        since_start_ms=round(t_http_ms, 1),
    )

    first_yield_done = False
    chunk_idx = 0
    total_out_chars = 0

    try:
        async for chunk in stream:
            chunk_idx += 1
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                text = delta.content
                if text:
                    if not first_yield_done:
                        first_yield_done = True
                        ttft_ms = (time.perf_counter() - t0) * 1000
                        chain_debug(
                            logger,
                            step="llm.chat_completion_stream",
                            event="FIRST_YIELD",
                            ttft_ms=round(ttft_ms, 1),
                            raw_chunks=chunk_idx,
                        )
                    total_out_chars += len(text)
                    yield text
    finally:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        chain_debug(
            logger,
            step="llm.chat_completion_stream",
            event="END",
            elapsed_ms=elapsed_ms,
            raw_chunks=chunk_idx,
            yielded_chars=total_out_chars,
            first_yield=first_yield_done,
        )


# ────────────────────────────────────────────────────────────────────
# get_embeddings — 对应 src/llm/client.py 的 LLMClient.get_embeddings()
# ────────────────────────────────────────────────────────────────────


async def get_embeddings(
    input_text: str,
    model: str = "embedding-model",
) -> List[float]:
    """
    获取向量嵌入 — 对应 src/llm/client.py 的 LLMClient.get_embeddings()。

    - 场景 A 使用 gateway 定义的 ``embedding-model`` 虚拟名
    - 场景 B 直连时需传入实际模型名（如 ``text-embedding-3-large``）
    """
    t0 = time.perf_counter()
    client = get_client()

    # 输入脱敏日志
    logger.debug("Embeddings Input (redacted): %s", redact_sensitive_info(input_text[:200]))

    chain_debug(
        logger,
        step="llm.get_embeddings",
        event="START",
        model=model,
        input_len=len(input_text),
        deployment_mode=settings.DEPLOYMENT_MODE.value,
    )

    try:
        response = await client.embeddings.create(
            input=input_text,
            model=model,
        )
        embedding = response.data[0].embedding
    except Exception:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        chain_debug(
            logger,
            step="llm.get_embeddings",
            event="ERROR",
            elapsed_ms=elapsed_ms,
        )
        logger.exception("[LLM] get_embeddings failed")
        raise

    elapsed_ms = (time.perf_counter() - t0) * 1000
    chain_debug(
        logger,
        step="llm.get_embeddings",
        event="END",
        elapsed_ms=elapsed_ms,
        dimensions=len(embedding),
    )
    return embedding


# ────────────────────────────────────────────────────────────────────
# parse_tool_calls
# ────────────────────────────────────────────────────────────────────


def parse_tool_calls(message: Any) -> list[dict]:
    """Extract tool calls from an LLM response message."""
    if not message.tool_calls:
        chain_debug(logger, step="llm.parse_tool_calls", event="NONE")
        return []
    results = []
    for tc in message.tool_calls:
        try:
            args = json.loads(tc.function.arguments)
        except (json.JSONDecodeError, TypeError):
            args = {}
        results.append(
            {
                "id": tc.id,
                "name": tc.function.name,
                "arguments": args,
            }
        )
    chain_debug(
        logger,
        step="llm.parse_tool_calls",
        event="OK",
        count=len(results),
        names=[r["name"] for r in results],
    )
    return results
