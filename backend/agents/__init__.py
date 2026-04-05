"""Agents package - imports all agents to trigger registration."""

# Import all agents to trigger their registration with the registry
from agents.log_analytics import LogAnalyticsAgent
from agents.jira_knowledge import JiraKnowledgeAgent
from agents.rca_synthesizer import RCASynthesizerAgent

__all__ = [
    "LogAnalyticsAgent",
    "JiraKnowledgeAgent",
    "RCASynthesizerAgent",
]
