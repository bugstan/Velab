"""
Tool Use 函数实现 — 供 Agent 调用的数据处理工具

这些工具函数在不依赖 LLM 的情况下工作，
通过数据库查询和日志文件操作提供结构化数据给 Agent。

工具列表：
1. extract_timeline_events  — 提取指定时间窗口的事件时间线
2. fetch_raw_line_context   — 获取原始日志上下文
3. search_fota_stage_transitions — 搜索 FOTA 阶段转换事件

作者：FOTA 诊断平台团队
创建时间：2026-04-06
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy import and_, func

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "logs"


def extract_timeline_events(
    db: Session,
    case_id: str,
    fault_time: Optional[datetime] = None,
    window_minutes: int = 15,
    source_types: Optional[List[str]] = None,
    levels: Optional[List[str]] = None,
    limit: int = 500,
) -> Dict[str, Any]:
    """
    提取指定时间窗口内的事件时间线

    根据故障时间点，提取前后 ±window_minutes 分钟内的所有事件，
    按时间排序，用于构建故障时间线。

    Args:
        db: 数据库会话
        case_id: 案件 ID
        fault_time: 故障发生时间点（为空时取所有事件）
        window_minutes: 时间窗口大小（单位：分钟，默认 ±15 分钟）
        source_types: 过滤日志源类型列表
        levels: 过滤日志级别列表
        limit: 最大返回事件数

    Returns:
        dict: {
            "case_id": str,
            "time_window": {"start": str, "end": str},
            "total_events": int,
            "events": [事件列表],
            "summary": {按 source_type 分组的计数}
        }
    """
    from models import DiagnosisEvent

    query = db.query(DiagnosisEvent).filter(DiagnosisEvent.case_id == case_id)

    start_time = None
    end_time = None

    if fault_time:
        start_time = fault_time - timedelta(minutes=window_minutes)
        end_time = fault_time + timedelta(minutes=window_minutes)
        query = query.filter(
            and_(
                DiagnosisEvent.normalized_ts >= start_time,
                DiagnosisEvent.normalized_ts <= end_time,
            )
        )

    if source_types:
        query = query.filter(DiagnosisEvent.source_type.in_(source_types))

    if levels:
        query = query.filter(DiagnosisEvent.level.in_(levels))

    events = query.order_by(DiagnosisEvent.normalized_ts.asc()).limit(limit).all()

    # 构建事件列表
    event_list = []
    source_summary: Dict[str, int] = {}
    for evt in events:
        event_list.append({
            "id": evt.id,
            "timestamp": evt.normalized_ts.isoformat() if evt.normalized_ts else None,
            "original_ts": evt.original_ts.isoformat() if evt.original_ts else None,
            "source_type": evt.source_type,
            "level": evt.level,
            "module": evt.module,
            "event_type": evt.event_type,
            "message": evt.message,
            "clock_confidence": evt.clock_confidence,
        })
        source_summary[evt.source_type] = source_summary.get(evt.source_type, 0) + 1

    return {
        "case_id": case_id,
        "time_window": {
            "start": start_time.isoformat() if start_time else None,
            "end": end_time.isoformat() if end_time else None,
            "window_minutes": window_minutes,
        },
        "total_events": len(event_list),
        "events": event_list,
        "summary_by_source": source_summary,
    }


def fetch_raw_line_context(
    db: Session,
    event_id: Optional[int] = None,
    file_id: Optional[str] = None,
    line_number: Optional[int] = None,
    context_lines: int = 5,
) -> Dict[str, Any]:
    """
    获取原始日志上下文

    根据事件 ID 或 (文件ID + 行号) 定位原始日志位置，
    返回该行前后各 context_lines 行的上下文。

    Args:
        db: 数据库会话
        event_id: 事件 ID（优先使用）
        file_id: 文件 ID（与 line_number 配合使用）
        line_number: 行号
        context_lines: 上下文行数（默认前后各 5 行）

    Returns:
        dict: {
            "event": 事件信息,
            "context_before": [前置行],
            "target_line": 目标行,
            "context_after": [后续行],
            "source_file": 文件路径
        }
    """
    from models import DiagnosisEvent, RawLogFile

    # 根据 event_id 定位
    target_event = None
    if event_id:
        target_event = db.query(DiagnosisEvent).filter_by(id=event_id).first()
        if target_event:
            file_id = target_event.file_id
            line_number = target_event.raw_line_number

    if not file_id or not line_number:
        return {
            "error": "需要提供 event_id 或 (file_id + line_number)",
            "context_before": [],
            "target_line": None,
            "context_after": [],
        }

    # 获取文件信息
    log_file = db.query(RawLogFile).filter_by(file_id=file_id).first()

    # 同时从数据库查询相邻事件作为上下文
    start_line = max(1, line_number - context_lines)
    end_line = line_number + context_lines

    nearby_events = (
        db.query(DiagnosisEvent)
        .filter(
            and_(
                DiagnosisEvent.file_id == file_id,
                DiagnosisEvent.raw_line_number >= start_line,
                DiagnosisEvent.raw_line_number <= end_line,
            )
        )
        .order_by(DiagnosisEvent.raw_line_number.asc())
        .all()
    )

    context_before = []
    target_line = None
    context_after = []

    for evt in nearby_events:
        line_info = {
            "line_number": evt.raw_line_number,
            "level": evt.level,
            "message": evt.message,
            "raw_snippet": evt.raw_snippet,
        }
        if evt.raw_line_number < line_number:
            context_before.append(line_info)
        elif evt.raw_line_number == line_number:
            target_line = line_info
        else:
            context_after.append(line_info)

    # 如果数据库中没有目标行，使用 raw_snippet
    if target_line is None and target_event and target_event.raw_snippet:
        target_line = {
            "line_number": line_number,
            "level": target_event.level,
            "message": target_event.message,
            "raw_snippet": target_event.raw_snippet,
        }

    return {
        "event_id": event_id,
        "file_id": file_id,
        "source_file": log_file.original_filename if log_file else None,
        "context_before": context_before,
        "target_line": target_line,
        "context_after": context_after,
    }


def search_fota_stage_transitions(
    db: Session,
    case_id: str,
    ecu_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    搜索 FOTA 阶段转换事件

    提取特定案件中的所有 FOTA 状态机阶段转换事件，
    按时间排序，用于追踪升级流程的完整生命周期。

    Args:
        db: 数据库会话
        case_id: 案件 ID
        ecu_name: ECU 名称过滤（如 iCGM, MPU, MCU）

    Returns:
        dict: {
            "case_id": str,
            "transitions": [阶段转换列表],
            "summary": {各阶段计数},
            "anomalies": [异常转换列表]
        }
    """
    from models import DiagnosisEvent

    # FOTA 阶段关键词
    STAGE_KEYWORDS = {
        "INIT": ["fota init", "update start", "ota begin", "upgrade start"],
        "VERSION_CHECK": ["version check", "query version", "check update"],
        "DOWNLOAD": ["download start", "downloading", "download package", "download finish"],
        "VERIFY": ["verify package", "checksum", "signature check", "verifyPackage"],
        "INSTALL": ["install start", "installing", "apply update", "flashing"],
        "REBOOT": ["reboot", "restart", "usb reboot", "usbReboot"],
        "ROLLBACK": ["rollback", "restore", "revert version", "fallback"],
        "COMPLETE": ["fota complete", "update success", "ota finish", "upgrade complete"],
        "FAILED": ["fota fail", "update error", "ota abort", "校验失败", "not exist"],
    }

    # 查询 FOTA 相关事件
    query = db.query(DiagnosisEvent).filter(DiagnosisEvent.case_id == case_id)

    if ecu_name:
        query = query.filter(
            DiagnosisEvent.message.ilike(f"%{ecu_name}%")
            | DiagnosisEvent.module.ilike(f"%{ecu_name}%")
        )

    events = query.order_by(DiagnosisEvent.normalized_ts.asc()).all()

    # 分类事件
    transitions = []
    stage_counts: Dict[str, int] = {}
    anomalies = []

    for evt in events:
        msg_lower = evt.message.lower()
        matched_stage = None

        for stage, keywords in STAGE_KEYWORDS.items():
            if any(kw in msg_lower for kw in keywords):
                matched_stage = stage
                break

        if matched_stage:
            transition = {
                "timestamp": evt.normalized_ts.isoformat() if evt.normalized_ts else None,
                "stage": matched_stage,
                "module": evt.module,
                "message": evt.message[:200],
                "level": evt.level,
                "event_id": evt.id,
            }
            transitions.append(transition)
            stage_counts[matched_stage] = stage_counts.get(matched_stage, 0) + 1

            # 检测异常转换
            if matched_stage == "FAILED":
                anomalies.append({
                    **transition,
                    "anomaly_type": "STAGE_FAILURE",
                    "description": f"阶段失败: {evt.message[:100]}",
                })
            elif matched_stage == "REBOOT" and stage_counts.get("REBOOT", 0) > 2:
                anomalies.append({
                    **transition,
                    "anomaly_type": "EXCESSIVE_REBOOT",
                    "description": f"多次重启 ({stage_counts['REBOOT']}次)，可能存在循环重启",
                })

    return {
        "case_id": case_id,
        "ecu_filter": ecu_name,
        "total_transitions": len(transitions),
        "transitions": transitions,
        "stage_summary": stage_counts,
        "anomalies": anomalies,
        "has_anomalies": len(anomalies) > 0,
    }


def clip_log_by_time_window(
    log_content: str,
    fault_time: datetime,
    window_minutes: int = 15,
) -> str:
    """
    按时间窗口裁剪日志内容

    根据故障时间点，从原始日志文本中提取 ±window_minutes 分钟内的行。
    支持多种常见日志时间戳格式。

    Args:
        log_content: 原始日志文本
        fault_time: 故障时间点
        window_minutes: 时间窗口（分钟）

    Returns:
        str: 裁剪后的日志文本
    """
    import re

    start = fault_time - timedelta(minutes=window_minutes)
    end = fault_time + timedelta(minutes=window_minutes)

    # 常见时间戳正则
    TS_PATTERNS = [
        # 2025-09-11 08:57:58.123
        (r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", "%Y-%m-%d %H:%M:%S"),
        # 09-11 08:57:58.123
        (r"(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", None),
        # 08:57:58
        (r"^(\d{2}:\d{2}:\d{2})", None),
    ]

    clipped_lines = []
    in_window = False

    for line in log_content.splitlines():
        line_time = None

        # 尝试从行中提取时间戳
        for pattern, fmt in TS_PATTERNS:
            m = re.search(pattern, line)
            if m:
                ts_str = m.group(1)
                try:
                    if fmt:
                        line_time = datetime.strptime(ts_str, fmt)
                    elif len(ts_str) > 10:
                        # MM-DD HH:MM:SS — 补充年份
                        line_time = datetime.strptime(
                            f"{fault_time.year}-{ts_str}", "%Y-%m-%d %H:%M:%S"
                        )
                    else:
                        # HH:MM:SS — 补充日期
                        line_time = datetime.strptime(ts_str, "%H:%M:%S").replace(
                            year=fault_time.year,
                            month=fault_time.month,
                            day=fault_time.day,
                        )
                except ValueError:
                    continue
                break

        if line_time:
            if start <= line_time <= end:
                in_window = True
                clipped_lines.append(line)
            elif in_window and line_time > end:
                break  # 已过窗口，停止
        elif in_window:
            # 没有时间戳的行（续行），如果在窗口内就保留
            clipped_lines.append(line)

    return "\n".join(clipped_lines)


# ── Workspace 工具函数 ──


async def read_workspace_file(
    workspace_path: str,
    filename: str = "notes.md",
) -> Dict[str, Any]:
    """
    读取工作区文件

    Agent 在执行前调用此工具读取当前诊断任务的
    工作区文件（如 focus.md / notes.md / todo.md），
    以理解全局上下文和其他 Agent 的已有发现。

    Args:
        workspace_path: 工作区根目录路径
        filename: 要读取的文件名 (默认 notes.md)

    Returns:
        dict: {
            "filename": str,
            "content": str | None,
            "exists": bool,
            "size_bytes": int
        }
    """
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
    """
    向工作区 notes.md 追加分析发现

    Agent 在完成分析后调用此工具，将关键发现写入
    notes.md 的专属 section 中。各 Agent 的 section
    以 ## {agent_name} 为标题隔离，互不干扰。

    Args:
        workspace_path: 工作区根目录路径
        agent_name: Agent 显示名称 (用作 section 标题)
        content: 要追加的 Markdown 格式分析发现

    Returns:
        dict: {"success": bool, "file": str, "section": str}
    """
    from services.workspace_manager import workspace_manager

    # 从路径中提取 task_id
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
    """
    更新工作区 todo.md 中的排查清单状态

    将指定的排查项标记为已完成 [x] 或未完成 [ ]。
    使用部分文本匹配定位目标行。

    Args:
        workspace_path: 工作区根目录路径
        item_text: 排查项文本（部分匹配即可）
        completed: True 标记为 [x]，False 标记为 [ ]

    Returns:
        dict: {"success": bool, "item": str, "new_status": str}
    """
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
