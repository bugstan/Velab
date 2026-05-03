"""Tests for RCASynthesizerAgent pure helper methods.

Only stateless, non-LLM methods are tested here:
  - _calculate_confidence
  - _validate_citations
  - _generate_executive_summary
  - _generate_recommendations
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pytest

from agents.rca_synthesizer import RCASynthesizerAgent
from agents.base import AgentResult


def _result(
    agent_name: str = "log_analytics",
    display_name: str = "Log Analytics",
    success: bool = True,
    confidence: str = "high",
    summary: str = "分析完成",
    detail: str = "",
    sources: Optional[list] = None,
) -> AgentResult:
    return AgentResult(
        agent_name=agent_name,
        display_name=display_name,
        success=success,
        confidence=confidence,
        summary=summary,
        detail=detail,
        sources=sources if sources is not None else [],
    )


@pytest.fixture
def agent() -> RCASynthesizerAgent:
    return RCASynthesizerAgent()


# ---------------------------------------------------------------------------
# _calculate_confidence
# ---------------------------------------------------------------------------

class TestCalculateConfidence:
    def test_all_high_returns_high(self, agent):
        results = [_result(confidence="high"), _result(confidence="high")]
        assert agent._calculate_confidence(results) == "high"

    def test_all_low_returns_low(self, agent):
        results = [_result(confidence="low"), _result(confidence="low")]
        assert agent._calculate_confidence(results) == "low"

    def test_mixed_high_low_returns_medium(self, agent):
        results = [_result(confidence="high"), _result(confidence="low")]
        assert agent._calculate_confidence(results) == "medium"

    def test_all_medium_returns_medium(self, agent):
        results = [_result(confidence="medium")]
        assert agent._calculate_confidence(results) == "medium"

    def test_empty_results_returns_low(self, agent):
        assert agent._calculate_confidence([]) == "low"

    def test_unknown_confidence_treated_as_low(self, agent):
        results = [_result(confidence="unknown"), _result(confidence="low")]
        assert agent._calculate_confidence(results) == "low"

    def test_two_high_one_medium_returns_high(self, agent):
        results = [
            _result(confidence="high"),
            _result(confidence="high"),
            _result(confidence="medium"),
        ]
        assert agent._calculate_confidence(results) == "high"


# ---------------------------------------------------------------------------
# _validate_citations
# ---------------------------------------------------------------------------

class TestValidateCitations:
    def test_valid_sources_no_warnings(self):
        sources = [{"title": "jira-001", "type": "jira"}]
        ar = _result(sources=[{"title": "jira-001", "type": "jira"}])
        warnings = RCASynthesizerAgent._validate_citations(sources, [ar])
        assert warnings == []

    def test_missing_title_field_warns(self):
        sources = [{"type": "jira"}]
        warnings = RCASynthesizerAgent._validate_citations(sources, [])
        assert any("title" in w for w in warnings)

    def test_missing_type_field_warns(self):
        sources = [{"title": "jira-001"}]
        warnings = RCASynthesizerAgent._validate_citations(sources, [])
        assert any("type" in w for w in warnings)

    def test_orphan_citation_warns(self):
        # source title not in any agent result → orphan
        sources = [{"title": "ghost-doc", "type": "doc"}]
        ar = _result(sources=[{"title": "other-doc", "type": "doc"}])
        warnings = RCASynthesizerAgent._validate_citations(sources, [ar])
        assert any("ghost-doc" in w for w in warnings)

    def test_duplicate_citation_warns(self):
        sources = [
            {"title": "jira-001", "type": "jira"},
            {"title": "jira-001", "type": "jira"},
        ]
        ar = _result(sources=[{"title": "jira-001", "type": "jira"}])
        warnings = RCASynthesizerAgent._validate_citations(sources, [ar])
        assert any("重复" in w for w in warnings)

    def test_empty_sources_no_warnings(self):
        warnings = RCASynthesizerAgent._validate_citations([], [])
        assert warnings == []

    def test_successful_agent_with_no_sources_warns(self):
        sources = []
        ar = _result(success=True, sources=[])
        warnings = RCASynthesizerAgent._validate_citations(sources, [ar])
        assert any("未提供引用来源" in w for w in warnings)


# ---------------------------------------------------------------------------
# _generate_executive_summary
# ---------------------------------------------------------------------------

class TestGenerateExecutiveSummary:
    def test_log_analytics_label(self, agent):
        results = [_result(agent_name="log_analytics", summary="检测到校验失败")]
        summary = agent._generate_executive_summary(results)
        assert "日志分析" in summary
        assert "检测到校验失败" in summary

    def test_jira_knowledge_label(self, agent):
        results = [_result(agent_name="jira_knowledge", summary="找到 3 个历史案例")]
        summary = agent._generate_executive_summary(results)
        assert "历史案例" in summary

    def test_unknown_agent_uses_display_name(self, agent):
        results = [_result(agent_name="custom_agent", display_name="自定义 Agent", summary="x")]
        summary = agent._generate_executive_summary(results)
        assert "自定义 Agent" in summary

    def test_empty_results_returns_fallback_message(self, agent):
        summary = agent._generate_executive_summary([])
        assert "未能生成" in summary

    def test_multiple_results_all_appear(self, agent):
        results = [
            _result(agent_name="log_analytics", summary="日志结论"),
            _result(agent_name="jira_knowledge", summary="Jira 结论"),
        ]
        summary = agent._generate_executive_summary(results)
        assert "日志结论" in summary
        assert "Jira 结论" in summary
