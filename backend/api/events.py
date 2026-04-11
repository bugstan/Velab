"""
事件查询和导出API

提供诊断事件的查询、过滤和导出功能
"""

import csv
import json
from io import StringIO
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from database import get_db
from models import DiagnosisEvent, Case
from api.schemas import (
    EventQuery,
    EventResponse,
    EventListResponse,
    EventExportRequest,
    ExportFormat
)

router = APIRouter()


@router.post("/query", response_model=EventListResponse)
def query_events(
    query_data: EventQuery,
    db: Session = Depends(get_db)
):
    """
    查询诊断事件
    
    支持多维度过滤:
    - 案例ID (必需)
    - 日志源类型
    - 事件类型
    - 模块名
    - 日志级别
    - 时间范围
    - 关键词搜索
    
    Args:
        query_data: 查询条件
        db: 数据库会话
        
    Returns:
        事件列表和总数
    """
    # 构建基础查询
    query = db.query(DiagnosisEvent).filter_by(case_id=query_data.case_id)
    
    # 应用过滤条件
    if query_data.source_type:
        query = query.filter(DiagnosisEvent.source_type == query_data.source_type)
    
    if query_data.event_type:
        query = query.filter(DiagnosisEvent.event_type == query_data.event_type)
    
    if query_data.module:
        query = query.filter(DiagnosisEvent.module == query_data.module)
    
    if query_data.level:
        query = query.filter(DiagnosisEvent.level == query_data.level)
    
    if query_data.start_time:
        query = query.filter(DiagnosisEvent.normalized_ts >= query_data.start_time)
    
    if query_data.end_time:
        query = query.filter(DiagnosisEvent.normalized_ts <= query_data.end_time)
    
    if query_data.keyword:
        # 关键词搜索(消息内容或模块名)
        keyword_filter = or_(
            DiagnosisEvent.message.ilike(f"%{query_data.keyword}%"),
            DiagnosisEvent.module.ilike(f"%{query_data.keyword}%")
        )
        query = query.filter(keyword_filter)
    
    # 获取总数
    total = query.count()
    
    # 分页查询(按时间排序)
    events = query.order_by(
        DiagnosisEvent.normalized_ts.asc()
    ).offset(query_data.offset).limit(query_data.limit).all()
    
    return EventListResponse(
        total=total,
        items=events,
        query=query_data
    )


@router.get("/{event_id}", response_model=EventResponse)
def get_event(
    event_id: int,
    db: Session = Depends(get_db)
):
    """
    获取单个事件详情
    
    Args:
        event_id: 事件ID
        db: 数据库会话
        
    Returns:
        事件详情
        
    Raises:
        HTTPException: 事件不存在时返回404
    """
    event = db.query(DiagnosisEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(
            status_code=404,
            detail=f"Event {event_id} not found"
        )
    
    return event


@router.get("/case/{case_id}/summary")
def get_case_event_summary(
    case_id: str,
    db: Session = Depends(get_db)
):
    """
    获取案例事件统计摘要
    
    返回事件的统计信息:
    - 总事件数
    - 按日志源分组统计
    - 按事件类型分组统计
    - 按日志级别分组统计
    - 时间范围
    
    Args:
        case_id: 案例ID
        db: 数据库会话
        
    Returns:
        统计摘要
    """
    from sqlalchemy import func
    
    # 检查案例是否存在
    case = db.query(Case).filter_by(case_id=case_id).first()
    if not case:
        raise HTTPException(
            status_code=404,
            detail=f"Case {case_id} not found"
        )
        
    # 总事件数
    total_events = db.query(func.count(DiagnosisEvent.id)).filter_by(case_id=case_id).scalar()
    
    if total_events == 0:
        return {
            "case_id": case_id,
            "total_events": 0,
            "by_source": {},
            "by_type": {},
            "by_level": {},
            "time_range": None
        }
    
    # 按日志源统计
    by_source = db.query(
        DiagnosisEvent.source_type,
        func.count(DiagnosisEvent.id).label('count')
    ).filter_by(case_id=case_id).group_by(DiagnosisEvent.source_type).all()
    
    # 按事件类型统计
    by_type = db.query(
        DiagnosisEvent.event_type,
        func.count(DiagnosisEvent.id).label('count')
    ).filter_by(case_id=case_id).group_by(DiagnosisEvent.event_type).all()
    
    # 按日志级别统计
    by_level = db.query(
        DiagnosisEvent.level,
        func.count(DiagnosisEvent.id).label('count')
    ).filter_by(case_id=case_id).group_by(DiagnosisEvent.level).all()
    
    # 时间范围
    time_range = db.query(
        func.min(DiagnosisEvent.normalized_ts).label('start'),
        func.max(DiagnosisEvent.normalized_ts).label('end')
    ).filter_by(case_id=case_id).first()
    
    return {
        "case_id": case_id,
        "total_events": total_events,
        "by_source": {row.source_type: row.count for row in by_source},
        "by_type": {row.event_type: row.count for row in by_type},
        "by_level": {row.level: row.count for row in by_level},
        "time_range": {
            "start": time_range.start.isoformat() if time_range.start else None,
            "end": time_range.end.isoformat() if time_range.end else None
        } if time_range else None
    }


@router.post("/export")
def export_events(
    export_data: EventExportRequest,
    db: Session = Depends(get_db)
):
    """
    导出事件数据
    
    支持JSON和CSV两种格式
    
    Args:
        export_data: 导出请求数据
        db: 数据库会话
        
    Returns:
        文件流响应
    """
    # 检查案例是否存在
    case = db.query(Case).filter_by(case_id=export_data.case_id).first()
    if not case:
        raise HTTPException(
            status_code=404,
            detail=f"Case {export_data.case_id} not found"
        )
        
    # 构建查询
    query = db.query(DiagnosisEvent).filter_by(case_id=export_data.case_id)
    
    if export_data.source_type:
        query = query.filter(DiagnosisEvent.source_type == export_data.source_type)
    
    if export_data.start_time:
        query = query.filter(DiagnosisEvent.normalized_ts >= export_data.start_time)
    
    if export_data.end_time:
        query = query.filter(DiagnosisEvent.normalized_ts <= export_data.end_time)
    
    # 获取事件(限制最多10000条)
    events = query.order_by(DiagnosisEvent.normalized_ts.asc()).limit(10000).all()
    
    if not events:
        raise HTTPException(
            status_code=404,
            detail="No events found matching the criteria"
        )
    
    # 根据格式导出
    if export_data.format == ExportFormat.JSON:
        return _export_json(events, export_data.case_id)
    else:
        return _export_csv(events, export_data.case_id)


def _export_json(events, case_id: str):
    """导出为JSON格式"""
    data = []
    for event in events:
        data.append({
            "id": event.id,
            "case_id": event.case_id,
            "file_id": event.file_id,
            "source_type": event.source_type,
            "original_ts": event.original_ts.isoformat() if event.original_ts else None,
            "normalized_ts": event.normalized_ts.isoformat() if event.normalized_ts else None,
            "clock_confidence": event.clock_confidence,
            "event_type": event.event_type,
            "module": event.module,
            "level": event.level,
            "message": event.message,
            "parsed_fields": event.parsed_fields,
            "raw_line_number": event.raw_line_number,
            "raw_snippet": event.raw_snippet
        })
    
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    
    return StreamingResponse(
        iter([json_str]),
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=events_{case_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        }
    )


def _export_csv(events, case_id: str):
    """导出为CSV格式"""
    output = StringIO()
    writer = csv.writer(output)
    
    # 写入表头
    writer.writerow([
        "id", "case_id", "file_id", "source_type",
        "original_ts", "normalized_ts", "clock_confidence",
        "event_type", "module", "level", "message",
        "raw_line_number", "raw_snippet"
    ])
    
    # 写入数据
    for event in events:
        writer.writerow([
            event.id,
            event.case_id,
            event.file_id,
            event.source_type,
            event.original_ts.isoformat() if event.original_ts else "",
            event.normalized_ts.isoformat() if event.normalized_ts else "",
            event.clock_confidence,
            event.event_type,
            event.module or "",
            event.level,
            event.message,
            event.raw_line_number or "",
            event.raw_snippet or ""
        ])
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=events_{case_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        }
    )
