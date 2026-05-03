"""
services/semantic_cache.py 单元测试

SemanticCacheService 使用 SQLAlchemy Session，通过 MagicMock 隔离 DB 调用。
覆盖：
- _hash_query          — 确定性、大小写/空白规范化
- get_cached_response  — cache MISS / HIT / JSON 解析错误
- set_cached_response  — 正常写入
- invalidate           — 按 query / cache_type / 全部过期
- get_stats            — 统计汇总
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

from services.semantic_cache import SemanticCacheService


def _make_db() -> MagicMock:
    """返回一个模拟的 SQLAlchemy Session。"""
    db = MagicMock()
    # execute().fetchone() 链式调用
    db.execute.return_value.fetchone.return_value = None
    return db


# ── _hash_query ────────────────────────────────────────────────────────────────

class TestHashQuery:
    def test_deterministic(self):
        svc = SemanticCacheService()
        h1 = svc._hash_query("same text", "s1")
        h2 = svc._hash_query("same text", "s1")
        assert h1 == h2

    def test_different_queries_different_hashes(self):
        svc = SemanticCacheService()
        assert svc._hash_query("query A", "") != svc._hash_query("query B", "")

    def test_different_scenarios_different_hashes(self):
        svc = SemanticCacheService()
        assert svc._hash_query("same", "s1") != svc._hash_query("same", "s2")

    def test_normalizes_whitespace_and_case(self):
        svc = SemanticCacheService()
        h1 = svc._hash_query("  Hello World  ", "")
        h2 = svc._hash_query("hello world", "")
        assert h1 == h2  # strip().lower() 后一致

    def test_returns_64_char_hex(self):
        h = SemanticCacheService._hash_query("test", "")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ── get_cached_response ────────────────────────────────────────────────────────

class TestGetCachedResponse:
    def test_miss_returns_none(self):
        svc = SemanticCacheService()
        db = _make_db()
        result = svc.get_cached_response(db, "no cache", scenario_id="sc1")
        assert result is None

    def test_hit_returns_parsed_json(self):
        svc = SemanticCacheService()
        db = _make_db()
        payload = {"diagnosis": "FW version mismatch", "confidence": 0.9}
        row = SimpleNamespace(
            id=1,
            response_text=json.dumps(payload),
            cache_type="exact",
            created_at=None,
            expires_at=None,
            hit_count=3,
        )
        db.execute.return_value.fetchone.return_value = row
        result = svc.get_cached_response(db, "query with cache", scenario_id="")
        assert result == payload

    def test_hit_updates_hit_count(self):
        svc = SemanticCacheService()
        db = _make_db()
        row = SimpleNamespace(id=42, response_text='{"ok":true}',
                              cache_type="exact", created_at=None,
                              expires_at=None, hit_count=0)
        db.execute.return_value.fetchone.return_value = row
        svc.get_cached_response(db, "query", scenario_id="")
        # 应调用两次 execute（SELECT + UPDATE hit_count）并提交
        assert db.execute.call_count == 2
        assert db.commit.called

    def test_invalid_json_returns_raw_response(self):
        svc = SemanticCacheService()
        db = _make_db()
        row = SimpleNamespace(id=1, response_text="not-json",
                              cache_type="exact", created_at=None,
                              expires_at=None, hit_count=0)
        db.execute.return_value.fetchone.return_value = row
        result = svc.get_cached_response(db, "q", scenario_id="")
        assert result == {"raw_response": "not-json"}


# ── set_cached_response ────────────────────────────────────────────────────────

class TestSetCachedResponse:
    def test_returns_query_hash(self):
        svc = SemanticCacheService()
        db = _make_db()
        h = svc.set_cached_response(db, "some query", {"result": "ok"}, scenario_id="")
        assert len(h) == 64

    def test_executes_upsert_and_commits(self):
        svc = SemanticCacheService()
        db = _make_db()
        svc.set_cached_response(db, "q", {"x": 1}, scenario_id="sc1")
        assert db.execute.called
        assert db.commit.called

    def test_zero_ttl_produces_no_expiry(self):
        svc = SemanticCacheService()
        db = _make_db()
        svc.set_cached_response(db, "q", {}, ttl_hours=0)
        _, kwargs = db.execute.call_args
        # expires_at 应为 None
        params = kwargs.get("params") or db.execute.call_args[0][1]
        assert params.get("expires") is None


# ── invalidate ────────────────────────────────────────────────────────────────

class TestInvalidate:
    def _setup_rowcount(self, db: MagicMock, count: int):
        db.execute.return_value.rowcount = count

    def test_invalidate_by_query_text(self):
        svc = SemanticCacheService()
        db = _make_db()
        self._setup_rowcount(db, 1)
        deleted = svc.invalidate(db, query_text="my query")
        assert deleted == 1
        assert db.commit.called

    def test_invalidate_by_cache_type(self):
        svc = SemanticCacheService()
        db = _make_db()
        self._setup_rowcount(db, 5)
        deleted = svc.invalidate(db, cache_type="exact")
        assert deleted == 5

    def test_invalidate_all_expired(self):
        svc = SemanticCacheService()
        db = _make_db()
        self._setup_rowcount(db, 3)
        deleted = svc.invalidate(db)
        assert deleted == 3


# ── get_stats ─────────────────────────────────────────────────────────────────

class TestGetStats:
    def test_returns_expected_keys(self):
        svc = SemanticCacheService()
        db = _make_db()
        db.execute.return_value.fetchone.return_value = SimpleNamespace(
            total_entries=10,
            total_hits=50,
            expired_entries=2,
            avg_hits=5.0,
        )
        stats = svc.get_stats(db)
        assert stats["total_entries"] == 10
        assert stats["total_hits"] == 50
        assert stats["expired_entries"] == 2
        assert stats["avg_hits_per_entry"] == 5.0

    def test_handles_none_values(self):
        svc = SemanticCacheService()
        db = _make_db()
        db.execute.return_value.fetchone.return_value = SimpleNamespace(
            total_entries=None, total_hits=None,
            expired_entries=None, avg_hits=None,
        )
        stats = svc.get_stats(db)
        assert stats["total_entries"] == 0
        assert stats["total_hits"] == 0
        assert stats["avg_hits_per_entry"] == 0.0
