"""
诊断工作区沙盒管理器 — Agent 共享记忆的文件系统层

为每个诊断任务创建独立的 Markdown 工作区，支持:
- 按 task_id 创建/销毁隔离的文件目录
- 模板初始化 (focus.md / notes.md / todo.md)
- 并发安全的 section 级追加写入
- 容量防护与自动降级

设计原则:
- 不替代 AgentResult，仅作为 LLM 友好的补充记忆层
- 任何 I/O 故障自动降级回纯 AgentResult 模式
- 各 Agent 只写自己的 section，互不干涉

作者：FOTA 诊断平台团队
创建时间：2026-04-06
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── 默认配置 ──
_DEFAULT_BASE_DIR = Path(__file__).resolve().parent.parent / "data" / "workspaces"
_DEFAULT_ARCHIVE_DIR = Path(__file__).resolve().parent.parent / "data" / "workspaces_archive"
_DEFAULT_MAX_SIZE_MB = 1024  # 总容量上限 1GB


@dataclass
class WorkspaceContext:
    """
    工作区句柄

    持有一个任务的工作区路径及内部锁，
    供 Agent 在 execute() 中通过 context 获取。
    """
    task_id: str
    workspace_dir: Path
    created_at: float = field(default_factory=time.time)
    _file_locks: dict[str, asyncio.Lock] = field(default_factory=dict, repr=False)

    def _get_lock(self, filename: str) -> asyncio.Lock:
        """获取文件级别的异步锁（懒初始化）"""
        if filename not in self._file_locks:
            self._file_locks[filename] = asyncio.Lock()
        return self._file_locks[filename]

    @property
    def focus_path(self) -> Path:
        return self.workspace_dir / "focus.md"

    @property
    def notes_path(self) -> Path:
        return self.workspace_dir / "notes.md"

    @property
    def todo_path(self) -> Path:
        return self.workspace_dir / "todo.md"


# ── 模板定义 ──

_FOCUS_TEMPLATE = """# 诊断任务总览

## 用户原始问题
{user_query}

## 场景
- **场景 ID**: {scenario_id}
- **任务 ID**: {task_id}
- **时间**: {timestamp}

## 已确认信息
- **涉及 ECU**: 待确认
- **故障阶段**: 待确认
- **错误码**: 待确认
"""

_NOTES_TEMPLATE = """# 分析笔记

> 各 Agent 在此记录分析发现，按 section 隔离。

"""

_TODO_TEMPLATE = """# 排查清单

- [ ] 日志阶段验证
- [ ] 异常模式识别
- [ ] 历史工单关联
- [ ] 技术文档匹配
- [ ] 根因综合分析
"""


class WorkspaceManager:
    """
    诊断工作区沙盒管理器

    核心能力:
    1. create()  — 创建独立工作区并初始化模板
    2. append()  — 向指定文件的指定 section 追加内容（并发安全）
    3. read()    — 读取工作区文件全文
    4. cleanup() — 任务完成后清理或归档
    """

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        archive_dir: Optional[Path] = None,
        max_total_size_mb: int = _DEFAULT_MAX_SIZE_MB,
        enabled: bool = True,
    ):
        self.base_dir = base_dir or _DEFAULT_BASE_DIR
        self.archive_dir = archive_dir or _DEFAULT_ARCHIVE_DIR
        self.max_total_size_mb = max_total_size_mb
        self.enabled = enabled
        self._workspaces: dict[str, WorkspaceContext] = {}

    # ── 核心方法 ──

    def create(
        self,
        task_id: str,
        user_query: str = "",
        scenario_id: str = "",
    ) -> Optional[WorkspaceContext]:
        """
        创建诊断工作区

        在 base_dir 下创建以 task_id 命名的目录，
        并初始化模板文件 (focus.md / notes.md / todo.md)。

        Args:
            task_id: 任务唯一标识
            user_query: 用户原始问题
            scenario_id: 诊断场景 ID

        Returns:
            WorkspaceContext: 工作区句柄；如果创建失败返回 None（降级模式）
        """
        if not self.enabled:
            return None

        try:
            # 容量防护
            if not self._check_capacity():
                logger.warning(
                    "Workspace capacity exceeded (%dMB limit), degrading to pure AgentResult mode",
                    self.max_total_size_mb,
                )
                return None

            workspace_dir = self.base_dir / task_id
            workspace_dir.mkdir(parents=True, exist_ok=True)

            from datetime import datetime, timezone
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            # 初始化模板文件
            (workspace_dir / "focus.md").write_text(
                _FOCUS_TEMPLATE.format(
                    user_query=user_query or "(未提供)",
                    scenario_id=scenario_id or "(未指定)",
                    task_id=task_id,
                    timestamp=timestamp,
                ),
                encoding="utf-8",
            )
            (workspace_dir / "notes.md").write_text(
                _NOTES_TEMPLATE,
                encoding="utf-8",
            )
            (workspace_dir / "todo.md").write_text(
                _TODO_TEMPLATE,
                encoding="utf-8",
            )

            ctx = WorkspaceContext(task_id=task_id, workspace_dir=workspace_dir)
            self._workspaces[task_id] = ctx

            logger.info("Workspace created: %s", workspace_dir)
            return ctx

        except (OSError, PermissionError) as e:
            logger.warning(
                "Workspace creation failed, degrading to pure AgentResult mode: %s", e
            )
            return None

    async def append(
        self,
        ctx: WorkspaceContext,
        filename: str,
        section: str,
        content: str,
    ) -> bool:
        """
        向工作区文件追加内容（并发安全）

        使用 asyncio.Lock 保护写入操作。每个 Agent 写入自己
        的 section（以 ## 为分隔），不触碰其他 Agent 的区域。

        Args:
            ctx: 工作区句柄
            filename: 目标文件名 (如 "notes.md")
            section: Agent 的 section 标题 (如 "日志分析 Agent")
            content: 要追加的 Markdown 内容

        Returns:
            bool: 是否写入成功
        """
        try:
            file_path = ctx.workspace_dir / filename
            lock = ctx._get_lock(filename)

            async with lock:
                existing = ""
                if file_path.exists():
                    existing = file_path.read_text(encoding="utf-8")

                # 构建 section 内容
                section_header = f"\n## {section}\n\n"
                section_content = f"{section_header}{content}\n"

                # 如果 section 已存在，追加到该 section 内部
                section_marker = f"## {section}"
                if section_marker in existing:
                    # 找到 section 结尾（下一个 ## 或文件末尾）
                    start = existing.index(section_marker)
                    rest = existing[start + len(section_marker):]
                    # 在该 section 结尾追加
                    next_section = rest.find("\n## ")
                    if next_section >= 0:
                        insert_pos = start + len(section_marker) + next_section
                        updated = (
                            existing[:insert_pos]
                            + f"\n{content}\n"
                            + existing[insert_pos:]
                        )
                    else:
                        updated = existing + f"\n{content}\n"
                else:
                    updated = existing + section_content

                file_path.write_text(updated, encoding="utf-8")

            return True

        except Exception as e:
            logger.warning("Workspace append failed (file=%s, section=%s): %s", filename, section, e)
            return False

    def read(self, ctx: WorkspaceContext, filename: str) -> Optional[str]:
        """
        读取工作区文件全文

        快照式读取，无需加锁。

        Args:
            ctx: 工作区句柄
            filename: 文件名 (如 "notes.md")

        Returns:
            str: 文件内容；文件不存在或读取失败时返回 None
        """
        try:
            file_path = ctx.workspace_dir / filename
            if file_path.exists():
                return file_path.read_text(encoding="utf-8")
            return None
        except Exception as e:
            logger.warning("Workspace read failed (file=%s): %s", filename, e)
            return None

    def cleanup(self, task_id: str, archive: bool = False) -> bool:
        """
        清理或归档工作区

        Args:
            task_id: 任务 ID
            archive: 是否归档（True: 移入 archive 目录；False: 直接删除）

        Returns:
            bool: 操作是否成功
        """
        try:
            workspace_dir = self.base_dir / task_id

            if not workspace_dir.exists():
                self._workspaces.pop(task_id, None)
                return True

            if archive:
                self.archive_dir.mkdir(parents=True, exist_ok=True)
                archive_path = self.archive_dir / f"{task_id}.tar.gz"
                import tarfile
                with tarfile.open(archive_path, "w:gz") as tar:
                    tar.add(workspace_dir, arcname=task_id)
                logger.info("Workspace archived: %s → %s", task_id, archive_path)

            shutil.rmtree(workspace_dir, ignore_errors=True)
            self._workspaces.pop(task_id, None)

            logger.info("Workspace cleaned: %s (archive=%s)", task_id, archive)
            return True

        except Exception as e:
            logger.warning("Workspace cleanup failed (task=%s): %s", task_id, e)
            return False

    def get(self, task_id: str) -> Optional[WorkspaceContext]:
        """获取已创建的工作区句柄"""
        return self._workspaces.get(task_id)

    # ── 容量防护 ──

    def _check_capacity(self) -> bool:
        """检查总容量是否在限制范围内"""
        if not self.base_dir.exists():
            return True

        total_bytes = sum(
            f.stat().st_size
            for f in self.base_dir.rglob("*")
            if f.is_file()
        )
        total_mb = total_bytes / (1024 * 1024)

        if total_mb >= self.max_total_size_mb:
            logger.warning(
                "Workspace total size %.1fMB exceeds limit %dMB",
                total_mb,
                self.max_total_size_mb,
            )
            return False

        return True

    def get_stats(self) -> dict:
        """获取工作区统计信息"""
        active_count = len(self._workspaces)
        total_bytes = 0

        if self.base_dir.exists():
            total_bytes = sum(
                f.stat().st_size
                for f in self.base_dir.rglob("*")
                if f.is_file()
            )

        return {
            "enabled": self.enabled,
            "active_workspaces": active_count,
            "total_size_mb": round(total_bytes / (1024 * 1024), 2),
            "max_size_mb": self.max_total_size_mb,
            "base_dir": str(self.base_dir),
        }


# ── 全局单例 ──

workspace_manager = WorkspaceManager()
