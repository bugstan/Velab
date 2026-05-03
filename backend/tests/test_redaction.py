"""
common/redaction.py 单元测试

覆盖：
- redact_sensitive_info — VIN / 手机号 / 车牌脱敏
- sensitive_redactor   — 异步装饰器输入/输出脱敏
"""

from __future__ import annotations

import logging
import pytest

from common.redaction import (
    SENSITIVE_PATTERNS,
    redact_sensitive_info,
    sensitive_redactor,
)


# ── redact_sensitive_info ────────────────────────────────────────────────────

class TestRedactSensitiveInfo:
    def test_redacts_valid_vin(self):
        text = "Vehicle VIN: LSVNV21B3FN123456 needs update"
        result = redact_sensitive_info(text)
        assert "LSVNV21B3FN123456" not in result
        assert "[REDACTED_VIN]" in result

    def test_preserves_text_around_vin(self):
        text = "VIN: LSVNV21B3FN123456 is the target"
        result = redact_sensitive_info(text)
        assert result.startswith("VIN: ")
        assert "is the target" in result

    def test_redacts_phone_number(self):
        text = "联系电话：13812345678，请及时回复"
        result = redact_sensitive_info(text)
        assert "13812345678" not in result
        assert "[REDACTED_PHONE]" in result

    def test_redacts_phone_various_prefixes(self):
        for prefix in ["130", "150", "170", "185", "199"]:
            phone = f"{prefix}12345678"
            text = f"phone={phone}"
            result = redact_sensitive_info(text)
            assert phone not in result
            assert "[REDACTED_PHONE]" in result

    def test_does_not_redact_short_number(self):
        text = "错误代码：1381234567"  # 10 位，不是手机号
        result = redact_sensitive_info(text)
        assert result == text

    def test_redacts_chinese_plate(self):
        text = "车牌 粤A12345 已完成升级"
        result = redact_sensitive_info(text)
        assert "粤A12345" not in result
        assert "[REDACTED_PLATE]" in result

    def test_redacts_new_energy_plate(self):
        text = "新能源车牌 沪AF12345 绑定成功"
        result = redact_sensitive_info(text)
        assert "沪AF12345" not in result
        assert "[REDACTED_PLATE]" in result

    def test_plain_text_unchanged(self):
        text = "升级成功，无敏感信息。"
        assert redact_sensitive_info(text) == text

    def test_empty_string(self):
        assert redact_sensitive_info("") == ""

    def test_multiple_sensitive_fields(self):
        text = "VIN=LSVNV21B3FN123456 手机=13812345678 车牌=京B88888"
        result = redact_sensitive_info(text)
        assert "LSVNV21B3FN123456" not in result
        assert "13812345678" not in result
        assert "京B88888" not in result
        assert result.count("[REDACTED_") == 3

    def test_sensitive_patterns_defines_three_keys(self):
        assert set(SENSITIVE_PATTERNS.keys()) == {"VIN", "PHONE", "PLATE"}


# ── sensitive_redactor 装饰器 ─────────────────────────────────────────────────

class TestSensitiveRedactor:
    @pytest.mark.asyncio
    async def test_passes_result_through(self):
        @sensitive_redactor
        async def dummy(messages: list) -> str:
            return "ok"

        result = await dummy([{"role": "user", "content": "hello"}])
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_logs_redacted_input(self, caplog):
        @sensitive_redactor
        async def dummy(messages: list) -> str:
            return "response"

        with caplog.at_level(logging.DEBUG, logger="common.redaction"):
            await dummy([{"role": "user", "content": "VIN是LSVNV21B3FN123456请处理"}])

        debug_msgs = "\n".join(caplog.messages)
        assert "LSVNV21B3FN123456" not in debug_msgs
        assert "[REDACTED_VIN]" in debug_msgs

    @pytest.mark.asyncio
    async def test_logs_redacted_output(self, caplog):
        @sensitive_redactor
        async def dummy(messages: list) -> str:
            return "回复：手机 13812345678 已绑定"

        with caplog.at_level(logging.DEBUG, logger="common.redaction"):
            await dummy([{"role": "user", "content": "test"}])

        debug_msgs = "\n".join(caplog.messages)
        assert "13812345678" not in debug_msgs

    @pytest.mark.asyncio
    async def test_reraises_exception(self):
        @sensitive_redactor
        async def failing(messages: list) -> str:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await failing([{"role": "user", "content": "x"}])

    @pytest.mark.asyncio
    async def test_kwargs_messages_extracted(self):
        @sensitive_redactor
        async def dummy(messages: list) -> str:
            return "ok"

        result = await dummy(messages=[{"role": "user", "content": "hi"}])
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_no_messages_arg_does_not_crash(self):
        @sensitive_redactor
        async def no_msg(query: str) -> str:
            return "result"

        result = await no_msg(query="some query")
        assert result == "result"
