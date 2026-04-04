"""
解析任务API

提供日志解析任务的提交和查询接口
"""

import uuid
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from database import get_db
from models import Case, RawLogFile, DiagnosisEvent
from models.log_file import ParseStatus
from api.schemas import (
    ParseTaskSubmit,
    ParseTaskResponse,
    SuccessResponse
)
from services.parser.base import ParserRegistry
from services.time_alignment import TimeAlignmentService
from services.event_normalizer import EventNormalizer
from db_operations import BatchOperations

router = APIRouter()

# 全局解析器注册表
parser_registry = ParserRegistry()

# 时间对齐服务
time_alignment = TimeAlignmentService()

# 事件标准化器
event_normalizer = EventNormalizer()


def _parse_single_file(
    file_id: str,
    case_id: str,
    time_window_start: Optional[datetime],
    time_window_end: Optional[datetime],
    max_lines: Optional[int],
    db: Session
) -> dict:
    """
    解析单个日志文件
    
    Args:
        file_id: 文件ID
        case_id: 案例ID
        time_window_start: 时间窗口起始
        time_window_end: 时间窗口结束
        max_lines: 最大行数
        db: 数据库会话
        
    Returns:
        解析结果统计
    """
    # 获取文件信息
    log_file = db.query(RawLogFile).filter_by(file_id=file_id).first()
    if not log_file:
        return {"success": False, "error": f"File {file_id} not found"}
    
    # 更新状态为解析中
    BatchOperations.update_file_parse_status(db, file_id, ParseStatus.PARSING)
    
    try:
        # 获取对应的解析器
        parser = parser_registry.get_parser(log_file.source_type)
        if not parser:
            raise ValueError(f"No parser found for source type: {log_file.source_type}")
        
        # 解析文件
        events = list(parser.parse_file(
            file_path=log_file.storage_path,
            time_window_start=time_window_start,
            time_window_end=time_window_end,
            max_lines=max_lines
        ))
        
        if not events:
            BatchOperations.update_file_parse_status(db, file_id, ParseStatus.PARSED)
            return {"success": True, "events_count": 0}
        
        # 转换为字典格式用于批量插入
        event_dicts = []
        for event in events:
            event_dict = {
                "case_id": case_id,
                "file_id": file_id,
                "source_type": event.source_type,
                "original_ts": event.original_ts,
                "normalized_ts": event.original_ts,  # 初始值,后续时间对齐会更新
                "clock_confidence": 1.0,
                "event_type": event.event_type.value if hasattr(event.event_type, 'value') else event.event_type,
                "module": event.module,
                "level": event.level.value if hasattr(event.level, 'value') else event.level,
                "message": event.message,
                "parsed_fields": event.parsed_fields,
                "raw_line_number": event.raw_line_number,
                "raw_snippet": event.raw_snippet
            }
            event_dicts.append(event_dict)
        
        # 批量插入事件
        inserted_count = BatchOperations.bulk_insert_events(db, event_dicts)
        
        # 更新状态为已解析
        BatchOperations.update_file_parse_status(db, file_id, ParseStatus.PARSED)
        
        return {"success": True, "events_count": inserted_count}
        
    except Exception as e:
        # 更新状态为失败
        BatchOperations.update_file_parse_status(
            db, file_id, ParseStatus.FAILED, error_msg=str(e)
        )
        return {"success": False, "error": str(e)}


def _parse_task_background(
    task_id: str,
    case_id: str,
    file_ids: List[str],
    time_window_start: Optional[datetime],
    time_window_end: Optional[datetime],
    max_lines: Optional[int]
):
    """
    后台任务: 执行解析任务
    
    Args:
        task_id: 任务ID
        case_id: 案例ID
        file_ids: 文件ID列表
        time_window_start: 时间窗口起始
        time_window_end: 时间窗口结束
        max_lines: 最大行数
    """
    from database import db_manager
    
    with db_manager.get_session() as db:
        total_events = 0
        failed_files = 0
        
        for file_id in file_ids:
            result = _parse_single_file(
                file_id, case_id, time_window_start, 
                time_window_end, max_lines, db
            )
            
            if result["success"]:
                total_events += result["events_count"]
            else:
                failed_files += 1
        
        # TODO: 更新任务状态到Redis或数据库
        print(f"Task {task_id} completed: {total_events} events, {failed_files} failed files")


@router.post("/submit", response_model=ParseTaskResponse, status_code=202)
def submit_parse_task(
    task_data: ParseTaskSubmit,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    提交解析任务
    
    创建异步解析任务,立即返回任务ID
    
    Args:
        task_data: 任务提交数据
        background_tasks: FastAPI后台任务
        db: 数据库会话
        
    Returns:
        任务信息
        
    Raises:
        HTTPException: 案例不存在时返回404
    """
    # 验证案例是否存在
    case = db.query(Case).filter_by(case_id=task_data.case_id).first()
    if not case:
        raise HTTPException(
            status_code=404,
            detail=f"Case '{task_data.case_id}' not found"
        )
    
    # 获取要解析的文件列表
    if task_data.file_ids:
        # 使用指定的文件列表
        files = db.query(RawLogFile).filter(
            RawLogFile.case_id == task_data.case_id,
            RawLogFile.file_id.in_(task_data.file_ids)
        ).all()
    else:
        # 解析该案例的所有待解析文件
        files = db.query(RawLogFile).filter(
            RawLogFile.case_id == task_data.case_id,
            RawLogFile.parse_status == ParseStatus.PENDING.value
        ).all()
    
    if not files:
        raise HTTPException(
            status_code=400,
            detail="No files to parse"
        )
    
    # 生成任务ID
    task_id = str(uuid.uuid4())
    
    # 提交后台任务
    file_ids = [f.file_id for f in files]
    background_tasks.add_task(
        _parse_task_background,
        task_id=task_id,
        case_id=task_data.case_id,
        file_ids=file_ids,
        time_window_start=task_data.time_window_start,
        time_window_end=task_data.time_window_end,
        max_lines=task_data.max_lines_per_file
    )
    
    # 返回任务信息
    return ParseTaskResponse(
        task_id=task_id,
        case_id=task_data.case_id,
        status="submitted",
        total_files=len(files),
        parsed_files=0,
        failed_files=0,
        total_events=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )


@router.get("/status/{task_id}", response_model=ParseTaskResponse)
def get_parse_task_status(
    task_id: str,
    db: Session = Depends(get_db)
):
    """
    查询解析任务状态
    
    Args:
        task_id: 任务ID
        db: 数据库会话
        
    Returns:
        任务状态信息
        
    Note:
        当前版本从数据库实时统计,后续可以集成Redis缓存任务状态
    """
    # TODO: 从Redis获取任务状态
    # 当前版本返回模拟数据
    return ParseTaskResponse(
        task_id=task_id,
        case_id="unknown",
        status="running",
        total_files=0,
        parsed_files=0,
        failed_files=0,
        total_events=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        error_message="Task status tracking not yet implemented. Check file parse_status instead."
    )


@router.post("/align-time/{case_id}", response_model=SuccessResponse)
def align_case_time(
    case_id: str,
    db: Session = Depends(get_db)
):
    """
    对案例的所有事件执行时间对齐
    
    Args:
        case_id: 案例ID
        db: 数据库会话
        
    Returns:
        成功响应
        
    Raises:
        HTTPException: 案例不存在或无事件时返回错误
    """
    # 验证案例是否存在
    case = db.query(Case).filter_by(case_id=case_id).first()
    if not case:
        raise HTTPException(
            status_code=404,
            detail=f"Case '{case_id}' not found"
        )
    
    # 获取所有事件
    events = db.query(DiagnosisEvent).filter_by(case_id=case_id).all()
    if not events:
        raise HTTPException(
            status_code=400,
            detail=f"No events found for case '{case_id}'"
        )
    
    # 转换为ParsedEvent格式
    from services.parser.base import ParsedEvent, EventLevel, EventType
    parsed_events = []
    for event in events:
        parsed_event = ParsedEvent(
            source_type=event.source_type,
            original_ts=event.original_ts,
            level=EventLevel(event.level) if event.level else EventLevel.INFO,
            event_type=EventType(event.event_type) if event.event_type else EventType.LOG,
            module=event.module,
            message=event.message,
            parsed_fields=event.parsed_fields,
            raw_line_number=event.raw_line_number,
            raw_snippet=event.raw_snippet
        )
        parsed_events.append(parsed_event)
    
    # 执行时间对齐
    alignment_result = time_alignment.align_events(parsed_events)
    
    # 更新数据库中的normalized_ts和clock_confidence
    for i, event in enumerate(events):
        normalized_ts = alignment_result.get_normalized_timestamp(
            parsed_events[i].source_type,
            parsed_events[i].original_ts
        )
        if normalized_ts:
            event.normalized_ts = normalized_ts.normalized_ts
            event.clock_confidence = normalized_ts.confidence
    
    db.commit()
    
    return SuccessResponse(
        success=True,
        message=f"Time alignment completed for case '{case_id}'",
        data={
            "status": alignment_result.status.value,
            "aligned_sources": len(alignment_result.offsets),
            "total_events": len(events)
        }
    )
