"""
解析任务API

提供日志解析任务的提交和查询接口（集成Arq异步任务队列）
"""

from datetime import datetime
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import Case, RawLogFile, DiagnosisEvent
from models.log_file import ParseStatus
from api.schemas import (
    ParseTaskSubmit,
    ParseTaskResponse,
    SuccessResponse
)
from services.time_alignment import TimeAlignmentService
from tasks.client import get_task_client

router = APIRouter()

# 时间对齐服务
time_alignment = TimeAlignmentService()


@router.post("/submit-bundle", response_model=ParseTaskResponse, status_code=202)
async def submit_bundle_task(
    file: UploadFile = File(..., description="日志压缩包或单日志文件"),
    case_id: str = Form(..., description="案例ID"),
    db: Session = Depends(get_db),
):
    """
    提交压缩包解析任务（统一进入 /api/parse 任务体系）。
    """
    case = db.query(Case).filter_by(case_id=case_id).first()
    if not case:
        case = Case(
            case_id=case_id,
            vin=None,
            vehicle_model="Unknown",
            issue_description="Auto created by bundle upload",
            status="active",
            meta_data={"auto_created": True},
        )
        db.add(case)
        db.commit()

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    upload_root = Path(settings.STORAGE_ROOT) / "uploads" / case_id
    upload_root.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    upload_name = file.filename or "upload.bin"
    upload_path = upload_root / f"{ts}_{upload_name}"
    upload_path.write_bytes(content)

    task_client = await get_task_client()
    task_id = await task_client.submit_bundle_task(
        case_id=case_id,
        upload_path=str(upload_path),
        upload_name=upload_name,
    )

    return ParseTaskResponse(
        task_id=task_id,
        case_id=case_id,
        status="pending",
        total_files=1,
        parsed_files=0,
        failed_files=0,
        total_events=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@router.post("/submit", response_model=ParseTaskResponse, status_code=202)
async def submit_parse_task(
    task_data: ParseTaskSubmit,
    db: Session = Depends(get_db)
):
    """
    提交解析任务（使用Arq异步任务队列）
    
    创建异步解析任务，立即返回任务ID
    
    Args:
        task_data: 任务提交数据
        db: 数据库会话
        
    Returns:
        任务信息
        
    Raises:
        HTTPException: 案例不存在或无文件可解析时返回错误
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
    
    # 获取任务客户端
    task_client = await get_task_client()
    
    # 提交任务到Arq队列
    file_ids = [f.file_id for f in files]
    time_start = task_data.time_window_start.isoformat() if task_data.time_window_start else None
    time_end = task_data.time_window_end.isoformat() if task_data.time_window_end else None
    
    task_id = await task_client.submit_parse_task(
        case_id=task_data.case_id,
        file_ids=file_ids,
        time_window_start=time_start,
        time_window_end=time_end,
        max_lines_per_file=task_data.max_lines_per_file
    )
    
    # 返回任务信息
    return ParseTaskResponse(
        task_id=task_id,
        case_id=task_data.case_id,
        status="pending",
        total_files=len(files),
        parsed_files=0,
        failed_files=0,
        total_events=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )


@router.get("/status/{task_id}")
async def get_parse_task_status(task_id: str):
    """
    查询解析任务状态（从Arq队列查询）
    
    Args:
        task_id: 任务ID
        
    Returns:
        任务状态信息
    """
    # 获取任务客户端
    task_client = await get_task_client()
    
    # 查询任务状态
    status = await task_client.get_task_status(task_id)
    
    return status


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
    
    # 按source_type分组
    events_by_source = {}
    for p_event in parsed_events:
        source = p_event.source_type
        if source not in events_by_source:
            events_by_source[source] = []
        events_by_source[source].append(p_event.to_dict())
    
    # 执行时间对齐
    alignment_result = time_alignment.align_events(events_by_source)
    
    # 更新数据库中的normalized_ts和clock_confidence
    for i, event in enumerate(events):
        res = alignment_result.get_normalized_timestamp(
            parsed_events[i].source_type,
            parsed_events[i].original_ts
        )
        if res:
            normalized_ts, confidence = res
            event.normalized_ts = normalized_ts
            event.clock_confidence = confidence
    
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
