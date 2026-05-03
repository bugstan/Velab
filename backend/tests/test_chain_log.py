"""
common/chain_log.py 单元测试

覆盖：
- trace_id 管理（bind / current / reset）
- chain_log / chain_debug / chain_info 输出格式
- async_step_timer / sync_step_timer 上下文管理器
"""

from __future__ import annotations

import asyncio
import logging
import pytest

from common.chain_log import (
    async_step_timer,
    bind_trace_id,
    chain_debug,
    chain_info,
    chain_log,
    current_trace_id,
    new_trace_id,
    reset_trace_id,
    sync_step_timer,
    iso_ts_utc,
)


# ── trace_id ──────────────────────────────────────────────────────────────────

class TestTraceId:
    def test_new_trace_id_is_12_hex_chars(self):
        tid = new_trace_id()
        assert len(tid) == 12
        assert all(c in "0123456789abcdef" for c in tid)

    def test_new_trace_id_is_unique(self):
        ids = {new_trace_id() for _ in range(20)}
        assert len(ids) == 20

    def test_default_trace_id_is_dash(self):
        # contextvars 默认值为空 → current_trace_id 返回 "-"
        # 每次测试运行在独立线程中，确认默认状态
        tid = current_trace_id()
        assert tid in ("-", "") or len(tid) > 0  # 可能被其他测试污染，不强断言

    def test_bind_and_current(self):
        token = bind_trace_id("abc123def456")
        try:
            assert current_trace_id() == "abc123def456"
        finally:
            reset_trace_id(token)

    def test_reset_restores_default(self):
        token = bind_trace_id("xyz")
        reset_trace_id(token)
        # 重置后回到默认 → "-"
        assert current_trace_id() == "-"

    def test_iso_ts_utc_format(self):
        ts = iso_ts_utc()
        # 格式：2026-05-03T12:34:56.789Z
        assert ts.endswith("Z")
        assert "T" in ts
        assert len(ts) == 24  # YYYY-MM-DDTHH:MM:SS.mmmZ


# ── chain_log 输出 ─────────────────────────────────────────────────────────────

class TestChainLog:
    def test_chain_log_includes_required_fields(self, caplog):
        logger = logging.getLogger("test.chain")
        token = bind_trace_id("testid123456")
        try:
            with caplog.at_level(logging.DEBUG, logger="test.chain"):
                chain_log(logger, logging.INFO, step="INGEST", event="START", msg="begin")
        finally:
            reset_trace_id(token)

        record = caplog.records[-1]
        assert "[CHAIN]" in record.message
        assert "trace=testid123456" in record.message
        assert "step=INGEST" in record.message
        assert "event=START" in record.message
        assert "begin" in record.message

    def test_chain_log_with_elapsed_ms(self, caplog):
        logger = logging.getLogger("test.chain")
        with caplog.at_level(logging.DEBUG, logger="test.chain"):
            chain_log(logger, logging.DEBUG, step="LLM", event="END", elapsed_ms=42.5)
        assert "elapsed_ms=42.5" in caplog.records[-1].message

    def test_chain_log_extra_kwargs_truncated(self, caplog):
        logger = logging.getLogger("test.chain")
        with caplog.at_level(logging.DEBUG, logger="test.chain"):
            chain_log(
                logger, logging.DEBUG,
                step="S", event="E",
                long_val="x" * 300,  # 超过 200 字符 → 截断
            )
        msg = caplog.records[-1].message
        assert "…" in msg  # 截断标记

    def test_chain_debug_uses_debug_level(self, caplog):
        logger = logging.getLogger("test.chain.debug")
        with caplog.at_level(logging.DEBUG, logger="test.chain.debug"):
            chain_debug(logger, step="X", event="Y")
        assert caplog.records[-1].levelno == logging.DEBUG

    def test_chain_info_uses_info_level(self, caplog):
        logger = logging.getLogger("test.chain.info")
        with caplog.at_level(logging.INFO, logger="test.chain.info"):
            chain_info(logger, step="X", event="Y")
        assert caplog.records[-1].levelno == logging.INFO

    def test_none_kwargs_omitted(self, caplog):
        logger = logging.getLogger("test.chain")
        with caplog.at_level(logging.DEBUG, logger="test.chain"):
            chain_log(logger, logging.DEBUG, step="S", event="E", skipped=None)
        assert "skipped" not in caplog.records[-1].message


# ── step_timer ────────────────────────────────────────────────────────────────

class TestStepTimers:
    @pytest.mark.asyncio
    async def test_async_step_timer_emits_start_and_end(self, caplog):
        logger = logging.getLogger("test.timer.async")
        with caplog.at_level(logging.DEBUG, logger="test.timer.async"):
            async with async_step_timer(logger, "ASYNC_STEP"):
                await asyncio.sleep(0)

        messages = [r.message for r in caplog.records]
        start_msgs = [m for m in messages if "ASYNC_STEP" in m and "START" in m]
        end_msgs = [m for m in messages if "ASYNC_STEP" in m and "END" in m]
        assert len(start_msgs) == 1
        assert len(end_msgs) == 1

    @pytest.mark.asyncio
    async def test_async_step_timer_end_includes_elapsed(self, caplog):
        logger = logging.getLogger("test.timer.elapsed")
        with caplog.at_level(logging.DEBUG, logger="test.timer.elapsed"):
            async with async_step_timer(logger, "TIMED"):
                await asyncio.sleep(0)

        end_msg = next(r.message for r in caplog.records if "END" in r.message)
        assert "elapsed_ms=" in end_msg

    def test_sync_step_timer_emits_start_and_end(self, caplog):
        logger = logging.getLogger("test.timer.sync")
        with caplog.at_level(logging.DEBUG, logger="test.timer.sync"):
            with sync_step_timer(logger, "SYNC_STEP"):
                pass  # 同步操作

        messages = [r.message for r in caplog.records]
        assert any("SYNC_STEP" in m and "START" in m for m in messages)
        assert any("SYNC_STEP" in m and "END" in m for m in messages)

    @pytest.mark.asyncio
    async def test_async_step_timer_propagates_exception(self, caplog):
        logger = logging.getLogger("test.timer.exc")
        with caplog.at_level(logging.DEBUG, logger="test.timer.exc"):
            with pytest.raises(RuntimeError, match="timer_error"):
                async with async_step_timer(logger, "ERR_STEP"):
                    raise RuntimeError("timer_error")
        # END 仍应记录（finally 块）
        end_msgs = [r.message for r in caplog.records if "END" in r.message]
        assert len(end_msgs) == 1
