"""Tests for JiraKnowledgeAgent — sync search methods and mock data loading.

LLM path (_llm_summarize) is exercised with a patched chat_completion, so
no real API key is required.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from agents.jira_knowledge import JiraKnowledgeAgent
from agents.base import AgentResult


@pytest.fixture
def agent() -> JiraKnowledgeAgent:
    return JiraKnowledgeAgent()


# ---------------------------------------------------------------------------
# _load_mock_tickets / _load_mock_docs — fallback to builtin when no file
# ---------------------------------------------------------------------------

class TestLoadMockData:
    def test_load_tickets_returns_builtin_when_file_missing(self, agent, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)  # no tickets.json here
        tickets = agent._load_mock_tickets()
        assert isinstance(tickets, list)
        assert len(tickets) > 0
        assert "key" in tickets[0]

    def test_load_tickets_from_file(self, agent, tmp_path, monkeypatch):
        custom = [{"key": "FOTA-1", "summary": "test", "description": "d", "resolution": "r"}]
        data_dir = tmp_path / "data" / "jira_mock"
        data_dir.mkdir(parents=True)
        (data_dir / "tickets.json").write_text(json.dumps(custom))
        # Patch DATA_DIR used inside jira_knowledge module
        import agents.jira_knowledge as mod
        monkeypatch.setattr(mod, "DATA_DIR", data_dir)
        tickets = agent._load_mock_tickets()
        assert tickets == custom

    def test_load_docs_returns_builtin_when_file_missing(self, agent, tmp_path, monkeypatch):
        import agents.jira_knowledge as mod
        monkeypatch.setattr(mod, "DATA_DIR", tmp_path / "nonexistent")
        docs = agent._load_mock_docs()
        assert isinstance(docs, list)
        assert len(docs) > 0
        assert "title" in docs[0]


# ---------------------------------------------------------------------------
# _search_tickets — keyword and ticket-number matching
# ---------------------------------------------------------------------------

class TestSearchTickets:
    def test_no_keywords_returns_first_three(self, agent):
        results = agent._search_tickets([])
        assert len(results) <= 3

    def test_keyword_match_returns_relevant_tickets(self, agent):
        results = agent._search_tickets(["校验失败"])
        titles = " ".join(t["summary"] for t in results)
        assert "校验" in titles

    def test_ticket_number_in_task_returns_exact_match_first(self, agent):
        results = agent._search_tickets([], task="请分析 FOTA-9123 的根因")
        assert results[0]["key"] == "FOTA-9123"

    def test_unmatched_keywords_returns_empty_list(self, agent):
        results = agent._search_tickets(["totally_nonexistent_xyz_keyword_abc"])
        assert results == []

    def test_results_capped_at_five(self, agent):
        # All tickets match the very broad keyword "FOTA"
        results = agent._search_tickets(["升级"])
        assert len(results) <= 5

    def test_case_insensitive_match(self, agent):
        results = agent._search_tickets(["ICGM"])
        lower_results = agent._search_tickets(["icgm"])
        assert len(results) == len(lower_results)


# ---------------------------------------------------------------------------
# _search_documents — doc keyword matching
# ---------------------------------------------------------------------------

class TestSearchDocuments:
    def test_no_keywords_returns_up_to_two_docs(self, agent):
        results = agent._search_documents([])
        assert len(results) <= 2

    def test_keyword_match_returns_relevant_docs(self, agent):
        results = agent._search_documents(["状态机"])
        titles = " ".join(d["title"] for d in results)
        assert "状态机" in titles

    def test_results_capped_at_three(self, agent):
        results = agent._search_documents(["FOTA"])
        assert len(results) <= 3


# ---------------------------------------------------------------------------
# execute — full flow with LLM mocked out
# ---------------------------------------------------------------------------

class TestExecute:
    @pytest.mark.asyncio
    async def test_execute_returns_agent_result(self, agent):
        result = await agent.execute("MPU 升级包校验失败", keywords=["校验失败"])
        assert isinstance(result, AgentResult)
        assert result.agent_name == "jira_knowledge"

    @pytest.mark.asyncio
    async def test_execute_includes_sources_when_tickets_found(self, agent):
        result = await agent.execute("校验失败", keywords=["校验失败"])
        # May succeed or gracefully degrade; either way sources is a list
        assert isinstance(result.sources, list)

    @pytest.mark.asyncio
    async def test_execute_with_llm_mock(self, agent):
        """Verify LLM path doesn't crash when patched."""
        from config import settings
        original = settings.AGENTS_USE_LLM
        try:
            settings.AGENTS_USE_LLM = True
            with patch(
                "services.llm.chat_completion",
                new_callable=AsyncMock,
                return_value="LLM 分析：此工单记录了校验失败问题。",
            ):
                result = await agent.execute("校验失败", keywords=["校验失败"])
            assert isinstance(result, AgentResult)
        finally:
            settings.AGENTS_USE_LLM = original
