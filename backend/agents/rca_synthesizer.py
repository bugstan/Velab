"""RCA Synthesizer Agent — 使用 LLM 进行多源证据交叉关联与根因推理。

职责：
  - 接收各诊断 Agent（日志/Jira/文档）的原始结果
  - 使用 synthesizer-model 做深度根因分析（交叉关联 + 因果链推理）
  - 输出结构化 Markdown 报告，作为最终用户可见内容
  - LLM 不可用时降级为模板拼接

下游 Response Generator 不再单独调用 LLM，仅负责流式输出本 Agent 的结果。
"""

from __future__ import annotations

import logging
from typing import List

from agents.base import BaseAgent, AgentResult, registry
from common.chain_log import sync_step_timer, chain_debug
from services.llm import chat_completion_stream

log = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
# RCA Synthesizer Prompt — 交叉关联 + 根因推理
# ────────────────────────────────────────────────────────────────────

RCA_SYSTEM_PROMPT = """\
你是一名资深车辆 FOTA（空中固件升级）诊断专家。

你将收到多个诊断 Agent 的分析结果（日志分析、历史工单、技术文档等），\
需要进行 **跨源证据交叉关联** 和 **因果链推理**，输出最终的结构化根因分析报告。

## 你的推理要求

1. **交叉关联**：将日志时间线、Jira 历史案例、技术文档规范相互印证，找出一致性证据和矛盾点
2. **因果链**：从现象出发，沿时间线和调用链推导出根因，标注每一步的证据强度
3. **置信度评估**：基于证据充分性给出整体置信度（高/中/低），并说明依据
4. **可操作建议**：给出具体的、可直接执行的修复步骤，不要泛泛而谈

## 输出格式（严格遵守）

## 信息分析

主要来源：[列出实际使用的数据来源名称]
置信度：[高/中/低] — [一句话说明置信度依据]

---

## 技术解答

### 关键发现

[核心根因结论，1-2 句话，明确指出故障原因]

### 因果链分析

[详细的时间线 + 因果推导，包含：
- 各 Agent 证据的交叉关联
- 具体时间戳、错误码、状态转换
- 矛盾证据的处理说明]

---

## ⚠️ 安全提示

[与车辆安全相关的注意事项；如无安全风险可写"当前故障不涉及行车安全"]

---

## 建议措施

[编号列表，包含具体可执行的修复/处理步骤]

---

## 规则
- 用中文回复
- 保留所有技术术语（ECU 名称、函数名、错误码等）用英文
- **必须引用**各 Agent 提供的具体数据（时间戳、字节数、状态码等），不要编造未提供的数据
- 如果 Agent 结果之间存在矛盾，明确指出并给出你的判断依据
- 如果某个 Agent 未找到信息（置信度低），坦诚说明该维度证据不足
- 如果整体证据不足以确定根因，给出最可能的假设和需要补充的信息"""


class RCASynthesizerAgent(BaseAgent):
    name = "rca_synthesizer"
    display_name = "RCA Synthesizer"
    description = (
        "综合多个Agent的分析结果，使用LLM进行跨源证据交叉关联与根因推理，"
        "生成结构化的最终诊断报告。"
    )

    async def execute(
        self,
        task: str,
        keywords: list[str] | None = None,
        context: dict | None = None,
    ) -> AgentResult:
        """
        使用 LLM 综合多路 Agent 的原始结果，输出根因分析报告。

        context 应包含：
          - agent_results: list[AgentResult]
          - workspace_path: str (可选)
        """
        with sync_step_timer(
            log,
            step="agent.rca_synthesizer",
            task_preview=task[:120],
        ):
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
                    detail="没有收到其他 Agent 的分析结果，无法进行综合分析。",
                    sources=[],
                )

            successful = [r for r in agent_results if r.success]
            if not successful:
                return AgentResult(
                    agent_name=self.name,
                    display_name=self.display_name,
                    success=False,
                    confidence="low",
                    summary="所有 Agent 分析均未成功",
                    detail="各个分析 Agent 均未能找到相关信息或分析失败。建议：\n"
                           "1. 检查日志文件是否已上传\n"
                           "2. 提供更具体的故障描述\n"
                           "3. 补充 ECU 名称、错误码等关键信息",
                    sources=[],
                )

            # 收集所有引用来源
            all_sources = []
            for ar in agent_results:
                all_sources.extend(ar.sources)

            # 读取 workspace notes 作为补充上下文
            workspace_notes = self._read_workspace_notes(context)

            # 组装 LLM 输入
            evidence_text = self._build_evidence_text(agent_results, workspace_notes)
            messages = [
                {"role": "system", "content": RCA_SYSTEM_PROMPT},
                {"role": "user", "content": f"用户问题：{task}\n\n{evidence_text}"},
            ]

            # 调用 LLM（synthesizer-model）
            try:
                accumulated = ""
                async for delta in chat_completion_stream(
                    messages,
                    max_tokens=4096,
                    model="synthesizer-model",
                ):
                    accumulated += delta

                chain_debug(
                    log,
                    step="agent.rca_synthesizer",
                    event="LLM_OK",
                    out_chars=len(accumulated),
                )

                confidence = self._calculate_confidence(successful)

                return AgentResult(
                    agent_name=self.name,
                    display_name=self.display_name,
                    success=True,
                    confidence=confidence,
                    summary=f"综合分析完成 — 基于 {len(successful)} 个 Agent 的证据交叉关联",
                    detail=accumulated,
                    sources=all_sources,
                    raw_data={
                        "agent_count": len(agent_results),
                        "successful_count": len(successful),
                        "confidence_scores": [r.confidence for r in successful],
                        "llm_used": True,
                    },
                )

            except Exception as e:
                chain_debug(
                    log,
                    step="agent.rca_synthesizer",
                    event="LLM_FALLBACK",
                    error_type=type(e).__name__,
                    error_msg=str(e)[:200],
                )
                log.exception("[RCASynthesizer] LLM unavailable, using template fallback")
                return self._template_fallback(task, agent_results, all_sources)

    # ── 内部方法 ──────────────────────────────────────────────────

    @staticmethod
    def _build_evidence_text(
        agent_results: List[AgentResult],
        workspace_notes: str = "",
    ) -> str:
        """将各 Agent 结果组装为 LLM 可读的证据文本。"""
        parts = ["## 各诊断 Agent 分析结果\n"]

        for ar in agent_results:
            status = "✅ 成功" if ar.success else "❌ 失败"
            parts.append(f"### {ar.display_name} [{status}] (置信度: {ar.confidence})")
            parts.append(f"**摘要**: {ar.summary}\n")
            if ar.detail:
                parts.append(ar.detail)
            if ar.sources:
                parts.append("\n**引用来源**:")
                for s in ar.sources:
                    parts.append(f"- [{s.get('type', 'unknown').upper()}] {s.get('title', '未知')}")
            parts.append("\n---\n")

        if workspace_notes:
            parts.append("## 工作区补充笔记\n")
            parts.append(workspace_notes)

        return "\n".join(parts)

    @staticmethod
    def _read_workspace_notes(context: dict | None) -> str:
        """读取工作区 notes.md 作为补充推理上下文（可选，降级安全）。"""
        if not context or "workspace_path" not in context:
            return ""
        try:
            from pathlib import Path
            notes_path = Path(context["workspace_path"]) / "notes.md"
            if notes_path.exists():
                content = notes_path.read_text(encoding="utf-8")
                log.debug("Workspace notes loaded: %d chars", len(content))
                return content
        except Exception as e:
            log.warning("Failed to read workspace notes: %s", e)
        return ""

    @staticmethod
    def _calculate_confidence(results: List[AgentResult]) -> str:
        """基于各 Agent 置信度的加权平均计算整体置信度。"""
        if not results:
            return "low"
        score_map = {"high": 3, "medium": 2, "low": 1}
        avg = sum(score_map.get(r.confidence, 1) for r in results) / len(results)
        if avg >= 2.5:
            return "high"
        elif avg >= 1.5:
            return "medium"
        return "low"

    def _template_fallback(
        self,
        task: str,
        agent_results: List[AgentResult],
        all_sources: list[dict],
    ) -> AgentResult:
        """LLM 不可用时的模板降级方案。"""
        successful = [r for r in agent_results if r.success]
        confidence = self._calculate_confidence(successful)

        source_names = [s.get("title", "未知") for s in all_sources] or ["系统日志"]

        parts = [
            f"## 信息分析\n\n主要来源：{'、'.join(source_names)}\n置信度：{confidence}\n\n---\n",
            "## 技术解答\n\n### 关键发现\n",
        ]
        for r in successful:
            parts.append(f"**{r.display_name}**: {r.summary}\n")
        parts.append("\n### 具体过程\n")
        for r in successful:
            if r.detail:
                parts.append(f"#### {r.display_name}\n{r.detail}\n\n")

        parts.append("---\n\n## 建议措施\n\n")
        parts.append("1. 根据上述分析结果对照排查\n")
        parts.append("2. 如信息不足，请补充更多日志或故障描述\n")
        parts.append("3. 参考历史类似案例的修复方案\n")
        parts.append("\n> ⚠️ 当前为降级模式（LLM 服务不可用），建议稍后重试以获得更精确的根因分析。\n")

        return AgentResult(
            agent_name=self.name,
            display_name=self.display_name,
            success=True,
            confidence=confidence,
            summary=f"综合分析完成（降级模式）— 基于 {len(successful)} 个 Agent 结果",
            detail="\n".join(parts),
            sources=all_sources,
            raw_data={
                "agent_count": len(agent_results),
                "successful_count": len(successful),
                "llm_used": False,
            },
        )


registry.register(RCASynthesizerAgent())
