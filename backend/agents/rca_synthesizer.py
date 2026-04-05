"""RCA Synthesizer Agent — synthesizes root cause analysis from multiple agent results."""

from __future__ import annotations

import logging
from typing import List

from agents.base import BaseAgent, AgentResult, registry
from common.chain_log import sync_step_timer

log = logging.getLogger(__name__)


class RCASynthesizerAgent(BaseAgent):
    name = "rca_synthesizer"
    display_name = "RCA Synthesizer"
    description = (
        "综合多个Agent的分析结果，生成最终的根因分析报告。"
        "汇总日志分析、历史案例、技术文档等多路证据，计算置信度，给出诊断结论和修复建议。"
    )

    async def execute(
        self, 
        task: str, 
        keywords: list[str] | None = None, 
        context: dict | None = None
    ) -> AgentResult:
        """
        Synthesize RCA from multiple agent results.
        
        Args:
            task: User's diagnostic query
            keywords: Extracted keywords
            context: Should contain 'agent_results' - list of AgentResult from other agents
        """
        with sync_step_timer(
            log,
            step="agent.rca_synthesizer",
            task_preview=task[:120],
        ):
            # Extract agent results from context
            agent_results: List[AgentResult] = []
            if context and "agent_results" in context:
                agent_results = context["agent_results"]
            
            if not agent_results:
                return AgentResult(
                    agent_name=self.name,
                    display_name=self.display_name,
                    success=False,
                    confidence="low",
                    summary="无法生成根因分析",
                    detail="没有收到其他Agent的分析结果，无法进行综合分析。",
                    sources=[],
                )
            
            # Synthesize results
            return self._synthesize_results(task, agent_results)
    
    def _synthesize_results(self, task: str, agent_results: List[AgentResult]) -> AgentResult:
        """Synthesize multiple agent results into a comprehensive RCA."""
        
        # Collect successful results
        successful_results = [r for r in agent_results if r.success]
        
        if not successful_results:
            return AgentResult(
                agent_name=self.name,
                display_name=self.display_name,
                success=False,
                confidence="low",
                summary="所有Agent分析均未成功",
                detail="各个分析Agent均未能找到相关信息或分析失败。建议：\n"
                       "1. 检查日志文件是否已上传\n"
                       "2. 提供更具体的故障描述\n"
                       "3. 补充ECU名称、错误码等关键信息",
                sources=[],
            )
        
        # Calculate overall confidence
        confidence = self._calculate_confidence(successful_results)
        
        # Build comprehensive analysis
        detail_parts = []
        all_sources = []
        
        # Add executive summary
        detail_parts.append("## 🎯 诊断结论\n")
        detail_parts.append(self._generate_executive_summary(successful_results))
        detail_parts.append("\n")
        
        # Add detailed analysis from each agent
        detail_parts.append("## 📊 详细分析\n")
        for result in successful_results:
            detail_parts.append(f"### {result.display_name}\n")
            detail_parts.append(f"**置信度**: {result.confidence}\n")
            detail_parts.append(f"**摘要**: {result.summary}\n\n")
            detail_parts.append(result.detail)
            detail_parts.append("\n\n")
            
            # Collect sources
            if result.sources:
                all_sources.extend(result.sources)
        
        # Add recommendations
        detail_parts.append("## 💡 修复建议\n")
        detail_parts.append(self._generate_recommendations(successful_results))
        
        # Add evidence references
        if all_sources:
            detail_parts.append("\n\n## 📚 证据来源\n")
            for idx, source in enumerate(all_sources, 1):
                source_type = source.get("type", "unknown")
                title = source.get("title", "未知来源")
                detail_parts.append(f"{idx}. [{source_type.upper()}] {title}\n")
        
        return AgentResult(
            agent_name=self.name,
            display_name=self.display_name,
            success=True,
            confidence=confidence,
            summary=f"综合分析完成 - 基于{len(successful_results)}个Agent的分析结果",
            detail="\n".join(detail_parts),
            sources=all_sources,
            raw_data={
                "agent_count": len(agent_results),
                "successful_count": len(successful_results),
                "confidence_scores": [r.confidence for r in successful_results],
            }
        )
    
    def _calculate_confidence(self, results: List[AgentResult]) -> str:
        """Calculate overall confidence based on individual agent confidences."""
        if not results:
            return "low"
        
        # Map confidence levels to scores
        confidence_map = {"high": 3, "medium": 2, "low": 1}
        
        scores = [confidence_map.get(r.confidence, 1) for r in results]
        avg_score = sum(scores) / len(scores)
        
        # Convert back to confidence level
        if avg_score >= 2.5:
            return "high"
        elif avg_score >= 1.5:
            return "medium"
        else:
            return "low"
    
    def _generate_executive_summary(self, results: List[AgentResult]) -> str:
        """Generate executive summary from agent results."""
        summaries = []
        
        for result in results:
            if result.agent_name == "log_analytics":
                summaries.append(f"**日志分析**: {result.summary}")
            elif result.agent_name == "jira_knowledge":
                summaries.append(f"**历史案例**: {result.summary}")
            else:
                summaries.append(f"**{result.display_name}**: {result.summary}")
        
        if not summaries:
            return "未能生成诊断结论。"
        
        return "\n".join(summaries)
    
    def _generate_recommendations(self, results: List[AgentResult]) -> str:
        """Generate actionable recommendations based on analysis."""
        recommendations = []
        
        # Extract recommendations from agent results
        for result in results:
            detail_lower = result.detail.lower()
            
            # Look for common patterns in analysis
            if "校验失败" in result.detail or "verify" in detail_lower:
                recommendations.append(
                    "1. **升级包校验机制优化**\n"
                    "   - 增加校验失败重试上限(建议max=3)\n"
                    "   - 实现校验失败后的自动回退机制\n"
                    "   - 增强文件完整性检查(MD5/SHA256)"
                )
            
            if "死循环" in result.detail or "循环" in result.detail:
                recommendations.append(
                    "2. **状态机保护机制**\n"
                    "   - 为关键状态添加超时保护\n"
                    "   - 实现异常状态的自动退出机制\n"
                    "   - 增加状态转换日志记录"
                )
            
            if "ecu" in detail_lower or "刷写" in result.detail:
                recommendations.append(
                    "3. **ECU刷写流程优化**\n"
                    "   - 优化ECU刷写顺序和依赖关系\n"
                    "   - 增加独立的超时保护机制\n"
                    "   - 实现刷写失败的回退策略"
                )
        
        # Add generic recommendations if none found
        if not recommendations:
            recommendations.append(
                "1. 建议收集更多日志信息进行深入分析\n"
                "2. 检查系统配置和环境参数\n"
                "3. 参考历史类似案例的修复方案"
            )
        
        return "\n\n".join(recommendations)


registry.register(RCASynthesizerAgent())
