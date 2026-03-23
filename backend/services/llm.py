"""LLM service — MiniMax via OpenAI-compatible SDK."""

from __future__ import annotations

import json
import logging
import time
from types import SimpleNamespace
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from common.chain_log import chain_debug
from config import (
    MINIMAX_API_KEY,
    MINIMAX_BASE_URL,
    MINIMAX_MODEL,
    MINIMAX_USE_HIGHSPEED,
)

logger = logging.getLogger(__name__)

# MiniMax 推理段标记（用 chr(96) 表示反引号，避免编辑/渲染破坏）
_BT = chr(96)
_THINK_OPEN = _BT + "think" + _BT
_THINK_CLOSE = _BT + "/think" + _BT

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=MINIMAX_API_KEY,
            base_url=MINIMAX_BASE_URL,
        )
    return _client


def _effective_model(*, use_highspeed: bool | None) -> str:
    """与流式逻辑一致：可选使用 *-highspeed 变体。"""
    want = MINIMAX_USE_HIGHSPEED if use_highspeed is None else use_highspeed
    m = MINIMAX_MODEL
    if want and not m.endswith("-highspeed"):
        return f"{m}-highspeed"
    return m


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
    """流式请求并在结束后聚合为与阻塞式相同的 message 形态（供 parse_tool_calls 使用）。"""
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


async def chat_completion(
    messages: list[dict],
    tools: list[dict] | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    *,
    stream: bool = False,
    use_highspeed: bool | None = None,
) -> Any:
    """
    Chat completion，返回 message（含 content / tool_calls）。
    stream=True：流式拉取后聚合，首包通常早于阻塞式；总时长视服务端而定。
    use_highspeed=None：遵循 config MINIMAX_USE_HIGHSPEED。
    """
    t0 = time.perf_counter()
    model = _effective_model(use_highspeed=use_highspeed)
    chain_debug(
        logger,
        step="llm.chat_completion",
        event="START",
        model=model,
        tools=bool(tools),
        msg_count=len(messages),
        max_tokens=max_tokens,
        stream_mode=stream,
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
    content_len = len((msg.content or ""))
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


async def chat_completion_stream(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    use_highspeed: bool | None = None,
) -> AsyncIterator[str]:
    """Streaming chat completion. use_highspeed=None 时跟随 config MINIMAX_USE_HIGHSPEED。"""
    t0 = time.perf_counter()
    client = get_client()
    model = _effective_model(use_highspeed=use_highspeed)

    chain_debug(
        logger,
        step="llm.chat_completion_stream",
        event="START",
        model=model,
        msg_count=len(messages),
        max_tokens=max_tokens,
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

    in_think = False
    first_yield_done = False
    chunk_idx = 0
    total_out_chars = 0

    try:
        async for chunk in stream:
            chunk_idx += 1
            delta = chunk.choices[0].delta
            if delta.content:
                text = delta.content
                while _THINK_OPEN in text:
                    in_think = True
                    text = text[: text.index(_THINK_OPEN)]
                if in_think and _THINK_CLOSE in text:
                    text = text[text.index(_THINK_CLOSE) + len(_THINK_CLOSE) :]
                    in_think = False
                if not in_think and text:
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


def parse_tool_calls(message) -> list[dict]:
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
        results.append({
            "id": tc.id,
            "name": tc.function.name,
            "arguments": args,
        })
    chain_debug(
        logger,
        step="llm.parse_tool_calls",
        event="OK",
        count=len(results),
        names=[r["name"] for r in results],
    )
    return results
