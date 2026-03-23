"""Agent base class and registry — extensible plugin architecture."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentResult:
    """Standardised output from any agent."""
    agent_name: str
    display_name: str
    success: bool
    confidence: str  # "high" | "medium" | "low"
    summary: str
    detail: str = ""
    sources: list[dict] = field(default_factory=list)
    raw_data: dict = field(default_factory=dict)


class BaseAgent(ABC):
    """All agents must inherit from this class."""

    name: str = ""
    display_name: str = ""
    description: str = ""  # shown to the Orchestrator LLM for tool selection

    def tool_schema(self) -> dict:
        """Convert this agent into an OpenAI function-calling tool definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "具体的分析任务描述，由 Orchestrator 根据用户问题生成",
                        },
                        "keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "从用户问题中提取的关键实体（ECU名称、错误码、时间等）",
                        },
                    },
                    "required": ["task"],
                },
            },
        }

    @abstractmethod
    async def execute(self, task: str, keywords: list[str] | None = None, context: dict | None = None) -> AgentResult:
        """Run the agent's analysis. Override in subclasses."""


class AgentRegistry:
    """Central registry. Agents register once, Orchestrator discovers them automatically."""

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        self._agents[agent.name] = agent

    def get(self, name: str) -> BaseAgent | None:
        return self._agents.get(name)

    def all_agents(self) -> list[BaseAgent]:
        return list(self._agents.values())

    def get_tools_schema(self, agent_names: list[str] | None = None) -> list[dict]:
        """Return OpenAI tools array for the specified (or all) agents."""
        agents = self._agents.values()
        if agent_names:
            agents = [a for a in agents if a.name in agent_names]
        return [a.tool_schema() for a in agents]

    def get_agent_descriptions(self, agent_names: list[str] | None = None) -> str:
        """Human-readable list for the Orchestrator system prompt."""
        agents = self._agents.values()
        if agent_names:
            agents = [a for a in agents if a.name in agent_names]
        lines = []
        for a in agents:
            lines.append(f"- **{a.display_name}** (`{a.name}`): {a.description}")
        return "\n".join(lines)


# Global singleton
registry = AgentRegistry()
