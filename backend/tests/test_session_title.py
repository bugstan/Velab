"""Tests for session title pure helper functions.

_fallback_title and _normalize_title contain non-trivial branch logic that
warrants direct unit coverage, independent of the LLM call path.
"""
from __future__ import annotations

import pytest

from api.session_title import (
    SessionTitleMessage,
    _fallback_title,
    _normalize_title,
)


# ---------------------------------------------------------------------------
# _fallback_title
# ---------------------------------------------------------------------------

def _msg(role: str, content: str) -> SessionTitleMessage:
    return SessionTitleMessage(role=role, content=content)


def test_fallback_title_returns_first_user_message_short():
    msgs = [_msg("user", "诊断 ECU 升级失败")]
    assert _fallback_title(msgs) == "诊断 ECU 升级失败"


def test_fallback_title_truncates_long_message():
    long = "A" * 50
    result = _fallback_title([_msg("user", long)])
    assert result.endswith("...")
    assert len(result) == 21  # 18 chars + "..."


def test_fallback_title_skips_assistant_messages():
    msgs = [
        _msg("assistant", "你好，我是助手"),
        _msg("user", "检查日志"),
    ]
    assert _fallback_title(msgs) == "检查日志"


def test_fallback_title_skips_empty_user_content():
    msgs = [
        _msg("user", "   "),
        _msg("user", "实际问题"),
    ]
    assert _fallback_title(msgs) == "实际问题"


def test_fallback_title_no_user_messages_returns_default():
    msgs = [_msg("assistant", "你好")]
    assert _fallback_title(msgs) == "新会话"


def test_fallback_title_empty_list_returns_default():
    assert _fallback_title([]) == "新会话"


def test_fallback_title_collapses_whitespace():
    msgs = [_msg("user", "ECU   升级   失败")]
    # Multiple spaces collapsed to single space
    result = _fallback_title(msgs)
    assert "  " not in result


# ---------------------------------------------------------------------------
# _normalize_title
# ---------------------------------------------------------------------------

def test_normalize_title_passthrough_clean_string():
    assert _normalize_title("ECU 升级失败分析", "fallback") == "ECU 升级失败分析"


def test_normalize_title_strips_title_prefix_english():
    assert _normalize_title("title: ECU 升级问题", "fb") == "ECU 升级问题"


def test_normalize_title_strips_title_prefix_case_insensitive():
    assert _normalize_title("Title: 日志分析", "fb") == "日志分析"


def test_normalize_title_strips_biaoti_colon_fullwidth():
    assert _normalize_title("标题：FOTA 升级失败", "fb") == "FOTA 升级失败"


def test_normalize_title_strips_biaoti_colon_halfwidth():
    assert _normalize_title("标题:FOTA 升级失败", "fb") == "FOTA 升级失败"


def test_normalize_title_strips_surrounding_quotes():
    assert _normalize_title('"ECU 分析"', "fb") == "ECU 分析"
    assert _normalize_title("'ECU 分析'", "fb") == "ECU 分析"
    assert _normalize_title("`ECU 分析`", "fb") == "ECU 分析"


def test_normalize_title_newline_replaced_with_space():
    result = _normalize_title("标题\n第二行", "fb")
    assert "\n" not in result


def test_normalize_title_empty_string_returns_fallback():
    assert _normalize_title("", "fallback") == "fallback"


def test_normalize_title_whitespace_only_returns_fallback():
    assert _normalize_title("   ", "fallback") == "fallback"


def test_normalize_title_truncates_at_30_chars():
    long = "A" * 50
    result = _normalize_title(long, "fb")
    assert len(result) == 30


def test_normalize_title_exact_30_chars_not_truncated():
    s = "A" * 30
    assert _normalize_title(s, "fb") == s
