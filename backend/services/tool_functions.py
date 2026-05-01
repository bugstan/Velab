"""
Tool Use 函数实现 — 供 Agent 调用的 workspace 操作工具。

旧的 DiagnosisEvent 时间线/上下文/阶段查询函数已随旧解析管线一并移除；
日志事件查询请走 log_pipeline 的 /api/bundles/{id}/events 与 /logs。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


async def read_workspace_file(
    workspace_path: str,
    filename: str = "notes.md",
) -> Dict[str, Any]:
    """读取工作区文件（focus.md / notes.md / todo.md）以理解全局上下文。"""
    file_path = Path(workspace_path) / filename
    try:
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")
            return {
                "filename": filename,
                "content": content,
                "exists": True,
                "size_bytes": len(content.encode("utf-8")),
            }
        return {
            "filename": filename,
            "content": None,
            "exists": False,
            "size_bytes": 0,
        }
    except Exception as e:
        logger.warning("read_workspace_file failed: %s", e)
        return {
            "filename": filename,
            "content": None,
            "exists": False,
            "size_bytes": 0,
            "error": str(e),
        }


async def append_workspace_notes(
    workspace_path: str,
    agent_name: str,
    content: str,
) -> Dict[str, Any]:
    """向工作区 notes.md 追加分析发现，按 Agent section 隔离。"""
    from services.workspace_manager import workspace_manager

    ws_dir = Path(workspace_path)
    task_id = ws_dir.name

    ctx = workspace_manager.get(task_id)
    if ctx is None:
        logger.warning("Workspace not found for task_id=%s, skipping notes append", task_id)
        return {"success": False, "file": "notes.md", "section": agent_name, "reason": "workspace_not_found"}

    success = await workspace_manager.append(ctx, "notes.md", agent_name, content)
    return {"success": success, "file": "notes.md", "section": agent_name}


async def update_todo_status(
    workspace_path: str,
    item_text: str,
    completed: bool = True,
) -> Dict[str, Any]:
    """更新工作区 todo.md 中匹配 ``item_text`` 的复选框状态。"""
    todo_path = Path(workspace_path) / "todo.md"
    new_mark = "[x]" if completed else "[ ]"
    old_mark = "[ ]" if completed else "[x]"

    try:
        if not todo_path.exists():
            return {"success": False, "item": item_text, "reason": "todo.md not found"}

        content = todo_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        updated = False

        for i, line in enumerate(lines):
            if item_text.lower() in line.lower() and old_mark in line:
                lines[i] = line.replace(old_mark, new_mark, 1)
                updated = True
                break

        if updated:
            todo_path.write_text("\n".join(lines), encoding="utf-8")
            return {"success": True, "item": item_text, "new_status": new_mark}
        else:
            return {"success": False, "item": item_text, "reason": "item_not_found_or_already_set"}

    except Exception as e:
        logger.warning("update_todo_status failed: %s", e)
        return {"success": False, "item": item_text, "error": str(e)}
