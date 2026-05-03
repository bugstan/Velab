"""Tests for DocRetrievalAgent.

vector_service.search_documents is mocked so no embedding model is needed.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.doc_retrieval import DocRetrievalAgent
from agents.base import AgentResult


_FAKE_DOCS = [
    {"title": "FOTA 状态机文档", "content": "状态机转换说明…", "excerpt": "状态机转换说明"},
    {"title": "刷写流程指南", "content": "刷写步骤详解…", "excerpt": "刷写步骤详解"},
]

_FAKE_RESULTS = [
    {"title": "FOTA 状态机文档", "excerpt": "状态机转换说明", "similarity_score": 0.75},
]


@pytest.fixture
def agent() -> DocRetrievalAgent:
    return DocRetrievalAgent()


# ---------------------------------------------------------------------------
# _load_documents — fallback when data dirs are absent or empty
# ---------------------------------------------------------------------------

class TestLoadDocuments:
    def test_returns_list_always(self, agent):
        # Real data dirs may or may not exist; result is always a list
        docs = agent._load_documents()
        assert isinstance(docs, list)

    def test_returns_builtin_fallback_when_dirs_missing(self, agent, monkeypatch):
        import agents.doc_retrieval as mod
        from pathlib import Path
        monkeypatch.setattr(mod, "DOC_DIR", Path("/nonexistent/path/docs"))
        monkeypatch.setattr(mod, "JIRA_DIR", Path("/nonexistent/path/jira"))
        docs = agent._load_documents()
        # No file-based docs; _BUILTIN_DOCS is returned as fallback
        assert isinstance(docs, list)
        assert len(docs) > 0
        # All returned items are from the builtin list (have title/excerpt)
        for d in docs:
            assert "title" in d


# ---------------------------------------------------------------------------
# execute — mocked vector_service
# ---------------------------------------------------------------------------

class TestExecute:
    @pytest.mark.asyncio
    async def test_returns_agent_result_with_documents(self, agent):
        with (
            patch.object(agent, "_load_documents", return_value=_FAKE_DOCS),
            patch("agents.doc_retrieval.vector_service.search_documents", return_value=_FAKE_RESULTS),
        ):
            result = await agent.execute("FOTA 升级状态机死循环")

        assert isinstance(result, AgentResult)
        assert result.success is True
        assert result.agent_name == "doc_retrieval"
        assert len(result.sources) == 1
        assert result.sources[0]["title"] == "FOTA 状态机文档"

    @pytest.mark.asyncio
    async def test_no_documents_returns_failure(self, agent):
        with patch.object(agent, "_load_documents", return_value=[]):
            result = await agent.execute("查询文档")

        assert result.success is False
        assert result.confidence == "low"

    @pytest.mark.asyncio
    async def test_no_search_results_returns_failure(self, agent):
        with (
            patch.object(agent, "_load_documents", return_value=_FAKE_DOCS),
            patch("agents.doc_retrieval.vector_service.search_documents", return_value=[]),
        ):
            result = await agent.execute("不存在的查询词 XYZ")

        assert result.success is False

    @pytest.mark.asyncio
    async def test_high_similarity_score_gives_medium_confidence(self, agent):
        high_score_result = [{**_FAKE_RESULTS[0], "similarity_score": 0.8}]
        with (
            patch.object(agent, "_load_documents", return_value=_FAKE_DOCS),
            patch("agents.doc_retrieval.vector_service.search_documents", return_value=high_score_result),
        ):
            result = await agent.execute("FOTA 状态机")

        assert result.confidence == "medium"

    @pytest.mark.asyncio
    async def test_low_similarity_score_gives_low_confidence(self, agent):
        low_score_result = [{**_FAKE_RESULTS[0], "similarity_score": 0.1}]
        with (
            patch.object(agent, "_load_documents", return_value=_FAKE_DOCS),
            patch("agents.doc_retrieval.vector_service.search_documents", return_value=low_score_result),
        ):
            result = await agent.execute("FOTA 状态机")

        assert result.confidence == "low"

    @pytest.mark.asyncio
    async def test_keywords_concatenated_into_query(self, agent):
        captured = {}

        def _capture(query, docs, **kwargs):
            captured["query"] = query
            return _FAKE_RESULTS

        with (
            patch.object(agent, "_load_documents", return_value=_FAKE_DOCS),
            patch("agents.doc_retrieval.vector_service.search_documents", side_effect=_capture),
        ):
            await agent.execute("升级失败", keywords=["校验", "eMMC"])

        assert "校验" in captured["query"]
        assert "eMMC" in captured["query"]

    @pytest.mark.asyncio
    async def test_llm_summarize_called_when_enabled(self, agent):
        from config import settings
        original = settings.AGENTS_USE_LLM
        try:
            settings.AGENTS_USE_LLM = True
            with (
                patch.object(agent, "_load_documents", return_value=_FAKE_DOCS),
                patch("agents.doc_retrieval.vector_service.search_documents", return_value=_FAKE_RESULTS),
                patch.object(
                    agent, "_llm_summarize",
                    new_callable=AsyncMock,
                    return_value=AgentResult(
                        agent_name="doc_retrieval",
                        display_name="文档检索 Agent",
                        success=True,
                        confidence="high",
                        summary="LLM 总结",
                        detail="",
                    ),
                ) as mock_llm,
            ):
                result = await agent.execute("FOTA 状态机")

            mock_llm.assert_awaited_once()
            assert result.summary == "LLM 总结"
        finally:
            settings.AGENTS_USE_LLM = original
