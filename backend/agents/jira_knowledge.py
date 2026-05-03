"""Jira / Knowledge Agent — searches Jira tickets and offline tech documents."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from agents.base import BaseAgent, AgentResult, registry
from common.chain_log import sync_step_timer
from config import settings

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "jira_mock"

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
你是 FOTA 历史工单分析专家。根据检索到的相关 Jira 工单和技术文档，对当前故障做历史案例关联分析。

**必须**按以下 Markdown 格式输出：

## 🔗 最相关历史案例
（指出最匹配的 1-2 个工单，说明与当前问题的相似点）

## 📋 历史修复方案
（提炼已验证的修复措施，分点列出）

## ⚠️ 注意事项
（历史案例中出现过的陷阱或需要特别注意的点）
"""


class JiraKnowledgeAgent(BaseAgent):
    name = "jira_knowledge"
    display_name = "Maxus Jira Agent"
    description = (
        "检索 Jira 历史工单和离线技术文档（PDF/PPT），查找类似故障案例和已知修复方案。"
        "适用于：查找历史修复经验、最佳实践、已知缺陷 (Known Issue) 等。"
    )

    async def execute(self, task: str, keywords: list[str] | None = None, context: dict | None = None) -> AgentResult:
        with sync_step_timer(
            log,
            step="agent.jira_knowledge",
            task_preview=task[:120],
            keywords=(keywords or [])[:8],
        ):
            if settings.AGENTS_USE_EMBEDDINGS:
                tickets = await self._search_tickets_embed(keywords or [], task)
                documents = await self._search_documents_embed(keywords or [], task)
            else:
                tickets = self._search_tickets(keywords or [], task)
                documents = self._search_documents(keywords or [])

            if not tickets and not documents:
                result = AgentResult(
                    agent_name=self.name,
                    display_name=self.display_name,
                    success=False,
                    confidence="low",
                    summary="未找到相关 Jira 工单或技术文档",
                    detail="在知识库中未检索到与查询直接相关的历史工单或文档。建议提供更具体的错误描述或 ECU 名称。",
                    sources=[],
                )
                await self._write_workspace(context, result)
                return result

            detail_parts: list[str] = []
            sources: list[dict] = []

            if tickets:
                detail_parts.append("**类似历史 Jira 工单：**\n")
                for t in tickets:
                    detail_parts.append(f"- **{t['key']}**: {t['summary']}")
                    detail_parts.append(f"  修复方案: {t['resolution']}\n")
                    sources.append({"title": f"{t['key']}: {t['summary']}", "type": "jira", "url": "#"})

            if documents:
                detail_parts.append("\n**相关离线文档：**\n")
                for d in documents:
                    detail_parts.append(f"- 《{d['title']}》")
                    detail_parts.append(f"  摘要: {d['excerpt']}\n")
                    sources.append({"title": d["title"], "type": "pdf", "url": "#"})

            result = AgentResult(
                agent_name=self.name,
                display_name=self.display_name,
                success=True,
                confidence="high" if tickets else "medium",
                summary=f"找到 {len(tickets)} 个相关工单，{len(documents)} 份相关文档",
                detail="\n".join(detail_parts),
                sources=sources,
            )

            # LLM 总结层：在检索结果基础上生成叙述性分析
            if settings.AGENTS_USE_LLM and (tickets or documents):
                try:
                    result = await self._llm_summarize(task, result)
                except Exception as exc:
                    log.warning("Jira LLM summarize failed, keeping retrieval result: %s", exc)

            await self._write_workspace(context, result)
            return result

    async def _llm_summarize(self, task: str, retrieval_result: AgentResult) -> AgentResult:
        """Use LLM to synthesize a narrative analysis from retrieved tickets/docs."""
        from services.llm import chat_completion

        user_msg = (
            f"当前故障描述：{task}\n\n"
            f"检索到的历史资料：\n{retrieval_result.detail}\n\n"
            "请对上述资料做历史案例关联分析。"
        )
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
        response = await chat_completion(messages, model="agent-model", temperature=0.3, max_tokens=1024)
        llm_text: str = getattr(response, "content", None) or ""
        if not llm_text.strip():
            return retrieval_result

        # 保留原始检索来源，只替换 detail
        return AgentResult(
            agent_name=retrieval_result.agent_name,
            display_name=retrieval_result.display_name,
            success=True,
            confidence=retrieval_result.confidence,
            summary=retrieval_result.summary,
            detail=llm_text.strip(),
            sources=retrieval_result.sources,
            raw_data={**(retrieval_result.raw_data or {}), "llm": True},
        )

    async def _write_workspace(self, context: dict | None, result: AgentResult) -> None:
        """将检索发现写入 workspace (可选，降级安全)"""
        if not context or "workspace_path" not in context:
            return
        try:
            from services.tool_functions import append_workspace_notes, update_todo_status
            ws_path = context["workspace_path"]

            notes_content = f"**摘要**: {result.summary}\n**置信度**: {result.confidence}\n\n{result.detail or '无结果'}"
            await append_workspace_notes(ws_path, self.display_name, notes_content)

            await update_todo_status(ws_path, "历史工单关联", completed=result.success)
        except Exception as e:
            log.warning("Workspace write failed in %s: %s", self.name, e)

    async def _search_tickets_embed(self, keywords: list[str], task: str) -> list[dict]:
        """Embedding 模式搜索 Jira 工单（语义相似度）。"""
        from services.vector_search import VectorSearchService
        try:
            svc = VectorSearchService(use_embeddings=True)
            tickets = self._load_mock_tickets()
            return await svc.async_search_jira_issues(task, tickets, top_k=5)
        except Exception as exc:
            log.warning("Embedding ticket search failed, falling back to keyword: %s", exc)
            return self._search_tickets(keywords, task)

    async def _search_documents_embed(self, keywords: list[str], task: str) -> list[dict]:
        """Embedding 模式搜索技术文档（语义相似度）。"""
        from services.vector_search import VectorSearchService
        try:
            svc = VectorSearchService(use_embeddings=True)
            docs = self._load_mock_docs()
            return await svc.async_search_documents(task, docs, top_k=3)
        except Exception as exc:
            log.warning("Embedding document search failed, falling back to keyword: %s", exc)
            return self._search_documents(keywords)

    def _search_tickets(self, keywords: list[str], task: str = "") -> list[dict]:
        """Search mock Jira tickets by keywords or ticket numbers extracted from task text."""
        import re
        tickets = self._load_mock_tickets()
        # 从 task 文本中直接提取工单号（如 FOTA-9123）
        ticket_refs = re.findall(r'[A-Z]+-\d+', task.upper())
        if ticket_refs:
            # 按工单号精确匹配的放在最前，再补充其他匹配结果
            exact = [t for t in tickets if t['key'].upper() in ticket_refs]
            rest_keywords = list(set(keywords) | {ref.split('-')[0] for ref in ticket_refs})
            fuzzy = [t for t in tickets if t not in exact]
            if rest_keywords:
                fuzzy = [t for t in fuzzy
                         if any(k.lower() in f"{t['key']} {t['summary']} {t['description']}".lower()
                                for k in rest_keywords)]
            return (exact + fuzzy)[:5]
        if not keywords:
            return tickets[:3]
        results = []
        for t in tickets:
            searchable = f"{t['key']} {t['summary']} {t['description']}".lower()
            if any(k.lower() in searchable for k in keywords):
                results.append(t)
        return results[:5]

    def _search_documents(self, keywords: list[str]) -> list[dict]:
        """Search mock document index."""
        docs = self._load_mock_docs()
        if not keywords:
            return docs[:2]
        results = []
        for d in docs:
            searchable = f"{d['title']} {d['excerpt']}".lower()
            if any(k.lower() in searchable for k in keywords):
                results.append(d)
        return results[:3]

    def _load_mock_tickets(self) -> list[dict]:
        path = DATA_DIR / "tickets.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return _BUILTIN_TICKETS

    def _load_mock_docs(self) -> list[dict]:
        path = DATA_DIR / "documents.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return _BUILTIN_DOCS


_BUILTIN_TICKETS = [
    {
        "key": "FOTA-8765",
        "summary": "iCGM 升级过程中挂死，根因为 eMMC 写入超时",
        "description": "在高温环境(>60°C)下 iCGM 执行 FOTA 升级，eMMC 写入操作超时导致升级包写入失败。状态机进入死循环，反复重试。",
        "resolution": "增加 eMMC 写入超时阈值至 60s，加入温度检测保护，超过 65°C 暂停升级。已在 v2.3.1 修复。",
    },
    {
        "key": "FOTA-9123",
        "summary": "MPU 升级包校验失败导致循环重启",
        "description": "MPU 升级包下载完成后 verifyPackage 失败，file size = 0。FOTA 客户端缺少校验失败重试上限，导致无限循环。",
        "resolution": "增加校验失败重试上限(max=3)，超限后自动回退到上一稳定版本。已在 v2.3.1 修复。",
    },
    {
        "key": "FOTA-7501",
        "summary": "ECU 刷写顺序依赖导致 IPK 刷写超时",
        "description": "升级流程中 IPK 依赖 iCGM 发送 FLASH_START 信号。当 iCGM 异常时 IPK 无限等待，无超时兜底。",
        "resolution": "为 IPK 增加独立的 300s 超时机制，超时后自动回退。已在 v2.4.0 修复。",
    },
    {
        "key": "FOTA-10234",
        "summary": "T-BOX 通信断连导致升级状态上报失败",
        "description": "升级过程中 T-BOX 与云端通信断连，导致升级状态无法上报，运维平台显示升级超时。实际升级已成功但状态不一致。",
        "resolution": "增加本地状态缓存，通信恢复后补报。增加离线状态机同步机制。已在 v2.5.0 修复。",
    },
]

_BUILTIN_DOCS = [
    {
        "title": "FOTA状态机流程及异常场景处理技术要点2023Q3.pdf",
        "excerpt": "详细描述了 FOTA 升级状态机的各个状态转换、异常场景处理流程，包括下载失败回退、校验失败重试、刷写超时保护等机制。",
    },
    {
        "title": "集中式升级刷写流程异常链路复盘2023-09",
        "excerpt": "复盘了 2023年9月期间多起集中式升级刷写异常案例，包括 iCGM 死循环、IPK 超时、MCU 状态不一致等问题的根因分析和修复方案。",
    },
    {
        "title": "FOTA客户端下载管理器设计文档v3.2",
        "excerpt": "HttpDownloadManager 的架构设计，包括断点续传、文件完整性校验(MD5/SHA256)、磁盘空间预检、并发下载控制等。",
    },
]


registry.register(JiraKnowledgeAgent())
