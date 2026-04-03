"""
Agent 基类和注册表 — 可扩展的插件架构

本模块定义了诊断 Agent 的基础架构，采用插件化设计：
1. AgentResult: 标准化的 Agent 执行结果数据类
2. BaseAgent: 所有 Agent 必须继承的抽象基类
3. AgentRegistry: 全局 Agent 注册表，支持自动发现和动态调用

设计特点：
- 插件式架构：新 Agent 只需继承 BaseAgent 并注册即可
- 标准化输出：所有 Agent 返回统一的 AgentResult 格式
- 自动工具生成：Agent 自动转换为 OpenAI function-calling 工具定义
- 场景化映射：支持根据不同场景选择不同的 Agent 组合

作者：FOTA 诊断平台团队
创建时间：2025
最后更新：2025
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentResult:
    """
    Agent 执行结果的标准化数据类
    
    所有 Agent 的 execute() 方法必须返回此类型，确保输出格式统一。
    
    Attributes:
        agent_name: Agent 的唯一标识符（如 "log_analytics"）
        display_name: Agent 的显示名称（如 "Log Analytics Agent"）
        success: 执行是否成功
        confidence: 结果置信度，可选值 "high" | "medium" | "low"
        summary: 简短摘要（1-2 句话）
        detail: 详细分析结果（支持 Markdown 格式）
        sources: 引用来源列表，每项包含 title、type、url 等字段
        raw_data: 原始数据字典，用于调试或后续处理
    """
    agent_name: str
    display_name: str
    success: bool
    confidence: str  # "high" | "medium" | "low"
    summary: str
    detail: str = ""
    sources: list[dict] = field(default_factory=list)
    raw_data: dict = field(default_factory=dict)


class BaseAgent(ABC):
    """
    Agent 抽象基类
    
    所有诊断 Agent 必须继承此类并实现 execute() 方法。
    基类提供了自动生成 OpenAI function-calling 工具定义的能力。
    
    子类必须定义的类属性：
        name: Agent 唯一标识符（小写下划线命名，如 "log_analytics"）
        display_name: 用户可见的显示名称（如 "日志分析 Agent"）
        description: Agent 功能描述，用于 LLM 选择合适的 Agent
    
    子类必须实现的方法：
        execute(): 执行诊断分析的核心逻辑
    """

    name: str = ""
    display_name: str = ""
    description: str = ""  # shown to the Orchestrator LLM for tool selection

    def tool_schema(self) -> dict:
        """
        将 Agent 转换为 OpenAI function-calling 工具定义
        
        自动生成符合 OpenAI function-calling 规范的工具定义，
        供 Orchestrator 在 LLM 调用时使用。
        
        Returns:
            dict: OpenAI function-calling 格式的工具定义，包含：
                - type: "function"
                - function.name: Agent 名称
                - function.description: Agent 描述
                - function.parameters: 参数定义（task 和 keywords）
        """
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
        """
        执行 Agent 的诊断分析逻辑（抽象方法）
        
        子类必须实现此方法，执行具体的诊断分析任务。
        
        Args:
            task: Orchestrator 生成的具体分析任务描述
            keywords: 从用户问题中提取的关键词列表（ECU 名称、错误码、时间等）
            context: 可选的上下文信息字典
        
        Returns:
            AgentResult: 标准化的分析结果
        
        Raises:
            可根据具体实现抛出相应异常，Orchestrator 会捕获并处理
        """


class AgentRegistry:
    """
    Agent 全局注册表
    
    采用单例模式，提供 Agent 的注册、查询和工具生成功能。
    Agent 在模块加载时自动注册，Orchestrator 通过注册表动态发现可用 Agent。
    
    主要功能：
    1. register(): 注册新 Agent
    2. get(): 根据名称获取 Agent 实例
    3. all_agents(): 获取所有已注册的 Agent
    4. get_tools_schema(): 生成 OpenAI function-calling 工具定义数组
    5. get_agent_descriptions(): 生成人类可读的 Agent 描述列表
    """

    def __init__(self) -> None:
        """初始化空的 Agent 字典"""
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """
        注册一个 Agent 到全局注册表
        
        Args:
            agent: 要注册的 Agent 实例
        """
        self._agents[agent.name] = agent

    def get(self, name: str) -> BaseAgent | None:
        """
        根据名称获取 Agent 实例
        
        Args:
            name: Agent 的唯一标识符
        
        Returns:
            BaseAgent | None: Agent 实例，不存在则返回 None
        """
        return self._agents.get(name)

    def all_agents(self) -> list[BaseAgent]:
        """
        获取所有已注册的 Agent 列表
        
        Returns:
            list[BaseAgent]: 所有 Agent 实例的列表
        """
        return list(self._agents.values())

    def get_tools_schema(self, agent_names: list[str] | None = None) -> list[dict]:
        """
        生成 OpenAI function-calling 工具定义数组
        
        将指定的（或所有）Agent 转换为 OpenAI function-calling 格式的工具定义，
        供 Orchestrator 在调用 LLM 时使用。
        
        Args:
            agent_names: 要包含的 Agent 名称列表，None 表示包含所有 Agent
        
        Returns:
            list[dict]: OpenAI tools 数组，每项为一个 Agent 的工具定义
        """
        agents = self._agents.values()
        if agent_names:
            agents = [a for a in agents if a.name in agent_names]
        return [a.tool_schema() for a in agents]

    def get_agent_descriptions(self, agent_names: list[str] | None = None) -> str:
        """
        生成人类可读的 Agent 描述列表
        
        用于 Orchestrator 的 system prompt，帮助 LLM 理解可用的 Agent 及其功能。
        
        Args:
            agent_names: 要包含的 Agent 名称列表，None 表示包含所有 Agent
        
        Returns:
            str: Markdown 格式的 Agent 描述列表，每行一个 Agent
        """
        agents = self._agents.values()
        if agent_names:
            agents = [a for a in agents if a.name in agent_names]
        lines = []
        for a in agents:
            lines.append(f"- **{a.display_name}** (`{a.name}`): {a.description}")
        return "\n".join(lines)


# 全局单例注册表
# 所有 Agent 模块在导入时会自动调用 registry.register() 注册自己
registry = AgentRegistry()
