"""
tests/test_vector_search_embedding.py

测试 VectorSearchService 的 embedding 模式：
- 真实 embedding 调用（mock get_embeddings）
- async_search_jira_issues / async_search_documents
- save_embed_index / load_embed_index 持久化
- fallback 逻辑（embedding 失败时退化到 TF-IDF）
"""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from services.vector_search import VectorSearchService


# ── 测试数据 ──────────────────────────────────────────────

TICKETS = [
    {
        "key": "FOTA-8765",
        "summary": "iCGM eMMC 写入超时",
        "description": "高温环境下写入超时",
        "resolution": "增加超时阈值",
    },
    {
        "key": "FOTA-9123",
        "summary": "MPU 升级包校验失败",
        "description": "verifyPackage 失败，file size = 0",
        "resolution": "增加重试上限",
    },
]

DOCS = [
    {
        "title": "FOTA 状态机流程",
        "excerpt": "INIT → DOWNLOAD → VERIFY → INSTALL → COMPLETE",
        "content": "每个阶段有独立超时保护",
    },
    {
        "title": "ECU 刷写顺序规范",
        "excerpt": "iCGM → IVI → MCU → IPK",
        "content": "iCGM 为升级协调者",
    },
]

# 模拟固定维度向量
DIMS = 8


def _fake_vec(seed: int) -> list[float]:
    """生成可复现的假向量，保证单位化以便余弦相似度有意义。"""
    import random
    rng = random.Random(seed)
    raw = [rng.gauss(0, 1) for _ in range(DIMS)]
    norm = math.sqrt(sum(x * x for x in raw)) or 1.0
    return [x / norm for x in raw]


# ── 单元测试 ───────────────────────────────────────────────

class TestCosineSimFloat:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert VectorSearchService._cosine_similarity_float(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert VectorSearchService._cosine_similarity_float([1, 0], [0, 1]) == pytest.approx(0.0)

    def test_empty_vectors_return_zero(self):
        assert VectorSearchService._cosine_similarity_float([], []) == 0.0

    def test_mismatched_dimensions_return_zero(self):
        assert VectorSearchService._cosine_similarity_float([1, 0], [1, 0, 0]) == 0.0

    def test_zero_vector_return_zero(self):
        assert VectorSearchService._cosine_similarity_float([0, 0], [1, 0]) == 0.0


class TestEmbedIndexPersistence:
    def test_save_and_load_roundtrip(self, tmp_path):
        svc = VectorSearchService(use_embeddings=True)
        svc._embed_vectors = [
            ("preview1", [0.1, 0.2, 0.3], {"id": 1}),
            ("preview2", [0.4, 0.5, 0.6], {"id": 2}),
        ]

        out = tmp_path / "test_index.json"
        saved = svc.save_embed_index(out)
        assert saved == 2
        assert out.exists()

        svc2 = VectorSearchService(use_embeddings=True)
        loaded = svc2.load_embed_index(out)
        assert loaded == 2
        assert svc2._embed_vectors[0][0] == "preview1"
        assert svc2._embed_vectors[1][2] == {"id": 2}

    def test_load_missing_file_returns_zero(self, tmp_path):
        svc = VectorSearchService(use_embeddings=True)
        count = svc.load_embed_index(tmp_path / "nonexistent.json")
        assert count == 0
        assert svc._embed_vectors == []

    def test_save_creates_parent_dirs(self, tmp_path):
        svc = VectorSearchService(use_embeddings=True)
        svc._embed_vectors = [("p", [0.1], {"x": 1})]
        deep = tmp_path / "a" / "b" / "c.json"
        svc.save_embed_index(deep)
        assert deep.exists()


class TestIndexWithEmbeddings:
    @pytest.mark.asyncio
    async def test_index_calls_get_embeddings_per_doc(self):
        svc = VectorSearchService(use_embeddings=True)
        call_count = [0]

        async def fake_embed(text):
            call_count[0] += 1
            return _fake_vec(call_count[0])

        with patch("services.llm.get_embeddings", side_effect=fake_embed):
            docs = [{"text": "doc1", "metadata": {"id": 1}}, {"text": "doc2", "metadata": {"id": 2}}]
            count = await svc._index_with_embeddings(docs, "text")

        assert count == 2
        assert call_count[0] == 2
        assert len(svc._embed_vectors) == 2

    @pytest.mark.asyncio
    async def test_index_skips_failed_embedding(self):
        svc = VectorSearchService(use_embeddings=True)
        call_count = [0]

        async def mixed_embed(text):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("API error")
            return _fake_vec(call_count[0])

        with patch("services.llm.get_embeddings", side_effect=mixed_embed):
            docs = [{"text": "ok"}, {"text": "fail"}, {"text": "ok2"}]
            count = await svc._index_with_embeddings(docs, "text")

        # 失败的文档被跳过，成功 2 条
        assert count == 2


class TestSearchWithEmbeddings:
    @pytest.mark.asyncio
    async def test_search_returns_sorted_results(self):
        svc = VectorSearchService(use_embeddings=True)
        # 预置两个向量：v1 与 query 完全相同，v2 正交
        query_vec = [1.0, 0.0]
        svc._embed_vectors = [
            ("low", [0.0, 1.0], {"id": "low"}),
            ("high", [1.0, 0.0], {"id": "high"}),
        ]

        with patch("services.llm.get_embeddings", AsyncMock(return_value=query_vec)):
            results = await svc._search_with_embeddings("any query", top_k=5, min_score=0.0)

        assert results[0]["metadata"]["id"] == "high"
        assert results[1]["metadata"]["id"] == "low"

    @pytest.mark.asyncio
    async def test_search_fallback_when_index_empty(self):
        """embedding 索引为空时应 fallback 到 TF-IDF。"""
        svc = VectorSearchService(use_embeddings=True)
        # 先建一个 TF-IDF 索引
        svc._index_with_tfidf([{"text": "eMMC timeout", "metadata": {"id": 1}}], "text")

        with patch("services.llm.get_embeddings", AsyncMock(return_value=[1.0])):
            results = await svc._search_with_embeddings("eMMC", top_k=5, min_score=0.0)

        # fallback 不会崩溃，且能返回结果
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_min_score_filter(self):
        svc = VectorSearchService(use_embeddings=True)
        svc._embed_vectors = [
            ("ortho", [0.0, 1.0], {"id": "ortho"}),   # cos=0 with [1,0]
            ("same", [1.0, 0.0], {"id": "same"}),      # cos=1 with [1,0]
        ]
        with patch("services.llm.get_embeddings", AsyncMock(return_value=[1.0, 0.0])):
            results = await svc._search_with_embeddings("q", top_k=5, min_score=0.5)

        assert len(results) == 1
        assert results[0]["metadata"]["id"] == "same"


class TestAsyncSearchJiraIssues:
    @pytest.mark.asyncio
    async def test_returns_list_with_similarity_score(self):
        svc = VectorSearchService(use_embeddings=True)
        call_count = [0]

        async def fake_embed(text):
            call_count[0] += 1
            return _fake_vec(call_count[0])

        with patch("services.llm.get_embeddings", side_effect=fake_embed):
            results = await svc.async_search_jira_issues("eMMC 超时", TICKETS, top_k=2)

        assert isinstance(results, list)
        assert len(results) <= 2
        for r in results:
            assert "key" in r
            assert "similarity_score" in r

    @pytest.mark.asyncio
    async def test_fallback_when_embedding_fails(self):
        """embedding API 全部失败时，async 方法应 fallback（空结果）而非抛异常。"""
        svc = VectorSearchService(use_embeddings=True)

        async def fail_embed(text):
            raise RuntimeError("No API key")

        with patch("services.llm.get_embeddings", side_effect=fail_embed):
            # _search_with_embeddings 会 fallback 到 TF-IDF（embed_vectors 为空）
            results = await svc.async_search_jira_issues("eMMC 超时", TICKETS, top_k=5)

        # 不崩溃即通过
        assert isinstance(results, list)


class TestAsyncSearchDocuments:
    @pytest.mark.asyncio
    async def test_returns_list_with_similarity_score(self):
        svc = VectorSearchService(use_embeddings=True)
        call_count = [0]

        async def fake_embed(text):
            call_count[0] += 1
            return _fake_vec(call_count[0])

        with patch("services.llm.get_embeddings", side_effect=fake_embed):
            results = await svc.async_search_documents("FOTA 状态机超时处理", DOCS, top_k=2)

        assert isinstance(results, list)
        assert len(results) <= 2
        for r in results:
            assert "title" in r
            assert "similarity_score" in r


class TestPublicAsyncInterface:
    """验证公共接口 index_documents / search 在 embedding 模式下正确 await 内部方法。"""

    @pytest.mark.asyncio
    async def test_index_documents_embedding_mode(self):
        svc = VectorSearchService(use_embeddings=True)
        call_count = [0]

        async def fake_embed(text):
            call_count[0] += 1
            return _fake_vec(call_count[0])

        with patch("services.llm.get_embeddings", side_effect=fake_embed):
            count = await svc.index_documents(
                [{"text": "doc1"}, {"text": "doc2"}], text_field="text"
            )

        assert count == 2
        assert len(svc._embed_vectors) == 2

    @pytest.mark.asyncio
    async def test_search_embedding_mode_returns_list(self):
        svc = VectorSearchService(use_embeddings=True)
        svc._embed_vectors = [
            ("doc1", [1.0, 0.0], {"id": 1}),
            ("doc2", [0.0, 1.0], {"id": 2}),
        ]

        with patch("services.llm.get_embeddings", AsyncMock(return_value=[1.0, 0.0])):
            results = await svc.search("查询", top_k=2, min_score=0.0)

        assert isinstance(results, list)
        assert results[0]["metadata"]["id"] == 1  # 最相似排在前面

    @pytest.mark.asyncio
    async def test_index_documents_tfidf_mode_is_sync_compatible(self):
        """TF-IDF 模式下 index_documents 仍可 await（同步返回值也可 await）。"""
        svc = VectorSearchService(use_embeddings=False)
        count = await svc.index_documents([{"text": "hello world"}], text_field="text")
        assert count == 1
