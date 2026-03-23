"""Jira / Knowledge Agent — searches Jira tickets and offline tech documents."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from agents.base import BaseAgent, AgentResult, registry
from common.chain_log import sync_step_timer

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "jira_mock"

log = logging.getLogger(__name__)


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
            tickets = self._search_tickets(keywords or [])
            documents = self._search_documents(keywords or [])

            if not tickets and not documents:
                return AgentResult(
                    agent_name=self.name,
                    display_name=self.display_name,
                    success=False,
                    confidence="low",
                    summary="未找到相关 Jira 工单或技术文档",
                    detail="在知识库中未检索到与查询直接相关的历史工单或文档。建议提供更具体的错误描述或 ECU 名称。",
                    sources=[],
                )

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

            return AgentResult(
                agent_name=self.name,
                display_name=self.display_name,
                success=True,
                confidence="high" if tickets else "medium",
                summary=f"找到 {len(tickets)} 个相关工单，{len(documents)} 份相关文档",
                detail="\n".join(detail_parts),
                sources=sources,
            )

    def _search_tickets(self, keywords: list[str]) -> list[dict]:
        """Search mock Jira tickets by keywords."""
        tickets = self._load_mock_tickets()
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
