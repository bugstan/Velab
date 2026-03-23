"""Log Analytics Agent — parses and analyses FOTA upgrade logs."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from agents.base import BaseAgent, AgentResult, registry
from common.chain_log import sync_step_timer

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "logs"

log = logging.getLogger(__name__)


class LogAnalyticsAgent(BaseAgent):
    name = "log_analytics"
    display_name = "Log Analytics Agent"
    description = (
        "分析车辆 FOTA 升级日志文件，定位异常时间线、错误码和故障根因。"
        "适用于：升级挂死、ECU刷写失败、校验异常、死循环、下载超时等问题。"
    )

    async def execute(self, task: str, keywords: list[str] | None = None, context: dict | None = None) -> AgentResult:
        with sync_step_timer(
            log,
            step="agent.log_analytics",
            task_preview=task[:120],
            keywords=(keywords or [])[:8],
        ):
            log_content = self._load_logs(keywords)

            if not log_content:
                return AgentResult(
                    agent_name=self.name,
                    display_name=self.display_name,
                    success=False,
                    confidence="low",
                    summary="未找到相关日志文件",
                    detail="当前日志目录中没有与查询关键词匹配的日志记录。请确认日志文件已放置在 data/logs/ 目录中。",
                    sources=[],
                )

            # When LLM is connected, send log_content + task to LLM for analysis.
            # For now, use mock analysis based on log content.
            analysis = self._mock_analyze(task, log_content, keywords or [])
            return analysis

    def _load_logs(self, keywords: list[str] | None) -> str:
        """Load log files from data/logs/. Filter by keywords if present."""
        if not DATA_DIR.exists():
            return ""

        all_content: list[str] = []
        for f in sorted(DATA_DIR.iterdir()):
            if f.suffix in (".log", ".txt"):
                text = f.read_text(encoding="utf-8", errors="ignore")
                if keywords:
                    relevant_lines = []
                    for line in text.splitlines():
                        low = line.lower()
                        if any(k.lower() in low for k in keywords):
                            relevant_lines.append(line)
                    if relevant_lines:
                        all_content.append(f"=== {f.name} ===\n" + "\n".join(relevant_lines))
                else:
                    all_content.append(f"=== {f.name} ===\n" + text)

        return "\n\n".join(all_content)

    def _mock_analyze(self, task: str, log_content: str, keywords: list[str]) -> AgentResult:
        """Mock analysis — returns realistic diagnostic results."""
        task_lower = task.lower()

        if any(k in task_lower for k in ["icgm", "挂死", "hang", "死循环"]):
            return AgentResult(
                agent_name=self.name,
                display_name=self.display_name,
                success=True,
                confidence="high",
                summary="iCGM 模块挂死根因分析完成",
                detail=(
                    "核心异常分析：\n\n"
                    "1. **MPU 升级包下载校验失败**\n"
                    "   - 时间戳: 08:57:58 — HttpDownloadManager 开始下载 2.077 GB MPU 升级包\n"
                    "   - 时间戳: 09:01:55 — 下载完成 (download finish)，但校验阶段报错\n"
                    "   - 关键错误: `verifyPackage: /data/fota/mpu_update.zip not exist`\n"
                    "   - 实际写入大小: `write file size = 0(0 B)`\n\n"
                    "2. **iCGM 模块进入死循环**\n"
                    "   - 时间戳: 09:02:09 — iCGM 检测到升级包校验失败\n"
                    "   - 触发 `[FotaFlashImpl]-usbReboot` 重启流程\n"
                    "   - 重启后再次尝试下载，形成\"下载 -> 校验失败 -> 重启 -> 再下载\"的死循环\n\n"
                    "3. **MCU/IPK 状态不一致**\n"
                    "   - MCU 已完成刷写进入等待状态\n"
                    "   - IPK 仍在等待 iCGM 完成升级协调\n"
                    "   - 状态机卡在 FLASHING_IN_PROGRESS\n\n"
                    "4. **USB 通信异常**\n"
                    "   - `[FotaFlashImpl]-usbReboot` 多次调用未能恢复正常状态\n"
                    "   - USB 设备枚举超时 (timeout=30000ms)"
                ),
                sources=[
                    {"title": "实际升级日志 (2025-09-11)", "type": "log"},
                ],
                raw_data={"log_lines_analyzed": len(log_content.splitlines())},
            )

        if any(k in task_lower for k in ["ecu", "刷写", "flash", "未完成"]):
            return AgentResult(
                agent_name=self.name,
                display_name=self.display_name,
                success=True,
                confidence="high",
                summary="ECU 刷写状态分析完成",
                detail=(
                    "ECU 刷写状态分析：\n\n"
                    "- IVI ECU: ✅ 刷写完成\n"
                    "- MCU ECU: ✅ 刷写完成\n"
                    "- IPK ECU: ❌ 未完成 — 等待 iCGM 协调信号\n"
                    "- iCGM ECU: ❌ 卡在校验失败循环\n\n"
                    "IPK 未完成刷写的直接原因是 iCGM 作为升级协调者进入死循环后，"
                    "未能向 IPK 发送 `FLASH_START` 协调信号。"
                ),
                sources=[
                    {"title": "实际升级日志 (2025-09-11)", "type": "log"},
                ],
            )

        # Fallback — generic log analysis
        return AgentResult(
            agent_name=self.name,
            display_name=self.display_name,
            success=True,
            confidence="medium",
            summary="日志分析完成",
            detail=f"已分析 {len(log_content.splitlines())} 行日志。在日志中搜索了关键词: {', '.join(keywords) if keywords else '无'}。\n\n未发现与查询直接相关的明显异常，建议提供更具体的 ECU 名称或错误描述。",
            sources=[{"title": "系统日志", "type": "log"}],
        )


registry.register(LogAnalyticsAgent())
