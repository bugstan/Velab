"""
Arq Worker 配置和任务定义

本模块定义异步任务的具体实现和 Worker 配置。
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

from arq import cron
from arq.connections import RedisSettings

from config import settings
from database import db_manager
from db_operations import BatchOperations
from models.log_file import ParseStatus
from services.parser import parser_registry
from services.time_alignment import TimeAlignmentService, LogEntry

logger = logging.getLogger(__name__)


async def parse_logs_task(
    ctx,
    case_id: str,
    file_ids: list[str],
    time_window_start: Optional[str] = None,
    time_window_end: Optional[str] = None,
    max_lines_per_file: Optional[int] = None,
) -> dict:
    """
    异步日志解析任务
    
    Args:
        ctx: Arq 上下文对象
        case_id: 案例ID
        file_ids: 待解析的日志文件ID列表
        time_window_start: 时间窗口起始（ISO格式）
        time_window_end: 时间窗口结束（ISO格式）
        max_lines_per_file: 每个文件最大解析行数
    
    Returns:
        dict: 任务执行结果
    """
    logger.info(f"开始解析任务 - Case: {case_id}, Files: {len(file_ids)}")
    
    # 初始化数据库连接
    db_manager.initialize()
    
    # 转换时间窗口
    time_start = datetime.fromisoformat(time_window_start) if time_window_start else None
    time_end = datetime.fromisoformat(time_window_end) if time_window_end else None
    
    total_events = 0
    parsed_files = 0
    failed_files = []
    
    try:
        with db_manager.get_session() as db:
            for file_id in file_ids:
                try:
                    # 获取文件信息
                    log_file = db.query(db_manager.models["RawLogFile"]).filter_by(file_id=file_id).first()
                    if not log_file:
                        logger.warning(f"文件不存在: {file_id}")
                        failed_files.append({"file_id": file_id, "error": "文件不存在"})
                        continue
                    
                    # 更新状态为解析中
                    BatchOperations.update_file_parse_status(db, file_id, ParseStatus.PARSING)
                    
                    # 获取对应的解析器
                    parser = parser_registry.get_parser(log_file.source_type)
                    if not parser:
                        logger.error(f"未找到解析器: {log_file.source_type}")
                        BatchOperations.update_file_parse_status(db, file_id, ParseStatus.FAILED)
                        failed_files.append({"file_id": file_id, "error": f"不支持的日志类型: {log_file.source_type}"})
                        continue
                    
                    # 解析日志文件
                    time_window = (time_start, time_end) if (time_start and time_end) else None
                    events = list(parser.parse_file(
                        file_path=Path(log_file.file_path),
                        time_window=time_window,
                        max_lines=max_lines_per_file,
                    ))
                    
                    if not events:
                        logger.warning(f"文件无有效事件: {file_id}")
                        BatchOperations.update_file_parse_status(db, file_id, ParseStatus.PARSED)
                        continue
                    
                    # 转换为数据库字段
                    event_dicts = []
                    for event in events:
                        event_dicts.append(
                            {
                                "case_id": case_id,
                                "file_id": file_id,
                                "source_type": event.source_type,
                                "original_ts": event.original_ts,
                                "normalized_ts": event.original_ts,
                                "clock_confidence": 1.0,
                                "event_type": event.event_type.value,
                                "module": event.module,
                                "level": event.level.value,
                                "message": event.message,
                                "raw_line_number": event.raw_line_number,
                                "raw_snippet": event.raw_snippet,
                                "parsed_fields": event.parsed_fields,
                                "parser_name": event.parser_name,
                                "parser_version": event.parser_version,
                            }
                        )
                    
                    # 批量插入事件
                    inserted_count = BatchOperations.bulk_insert_events(db, event_dicts)
                    total_events += inserted_count
                    
                    # 更新文件状态为已解析
                    BatchOperations.update_file_parse_status(db, file_id, ParseStatus.PARSED)
                    parsed_files += 1
                    
                    logger.info(f"文件解析完成: {file_id}, 事件数: {inserted_count}")
                    
                except Exception as e:
                    logger.error(f"解析文件失败 {file_id}: {str(e)}", exc_info=True)
                    BatchOperations.update_file_parse_status(db, file_id, ParseStatus.FAILED)
                    failed_files.append({"file_id": file_id, "error": str(e)})
            
            # 如果有成功解析的文件，执行时间对齐
            if parsed_files > 0:
                try:
                    logger.info(f"开始时间对齐 - Case: {case_id}")
                    alignment_service = TimeAlignmentService()
                    
                    # 获取该案例的所有事件
                    events_query = db.query(db_manager.models["DiagnosisEvent"]).filter_by(case_id=case_id)
                    all_events = events_query.all()
                    
                    if all_events:
                        events_by_source: dict[str, list[LogEntry]] = {}
                        for e in all_events:
                            events_by_source.setdefault(e.source_type, []).append(
                                LogEntry(
                                    source=e.source_type,
                                    message=e.message or "",
                                    wall_time=e.original_ts,
                                    raw_time=e.original_ts.isoformat() if e.original_ts else "",
                                )
                            )

                        # 执行时间对齐
                        alignment_result = alignment_service.align_events(events_by_source)

                        # 批量更新对齐后的时间戳与置信度
                        updates = []
                        for e in all_events:
                            if e.original_ts is None:
                                continue
                            normalized_ts, confidence = alignment_result.get_normalized_timestamp(
                                e.source_type,
                                e.original_ts,
                            )
                            updates.append(
                                {
                                    "id": e.id,
                                    "normalized_ts": normalized_ts,
                                    "clock_confidence": confidence,
                                }
                            )

                        if updates:
                            db.bulk_update_mappings(db_manager.models["DiagnosisEvent"], updates)
                            db.commit()
                        logger.info(f"时间对齐完成 - Case: {case_id}, 状态: {alignment_result.status}")
                        
                except Exception as e:
                    logger.error(f"时间对齐失败 - Case: {case_id}: {str(e)}", exc_info=True)
        
        result = {
            "case_id": case_id,
            "total_files": len(file_ids),
            "parsed_files": parsed_files,
            "failed_files": len(failed_files),
            "total_events": total_events,
            "failures": failed_files,
            "status": "completed" if not failed_files else "partial_success",
        }
        
        logger.info(f"解析任务完成 - {result}")
        return result
        
    except Exception as e:
        logger.error(f"解析任务失败 - Case: {case_id}: {str(e)}", exc_info=True)
        return {
            "case_id": case_id,
            "status": "failed",
            "error": str(e),
        }
    finally:
        db_manager.close()


async def cleanup_old_tasks(ctx):
    """
    定期清理过期任务记录（示例定时任务）
    
    Args:
        ctx: Arq 上下文对象
    """
    logger.info("执行定时清理任务")
    # 这里可以添加清理逻辑，例如删除30天前的任务记录
    return {"cleaned": 0}


class WorkerSettings:
    """
    Arq Worker 配置类
    
    定义 Redis 连接、任务函数、重试策略等配置。
    """
    # Redis 连接配置
    redis_settings = RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
    )
    
    # 注册的任务函数
    functions = [parse_logs_task]
    
    # 定时任务（可选）
    cron_jobs = [
        cron(cleanup_old_tasks, hour=2, minute=0),  # 每天凌晨2点执行清理
    ]
    
    # Worker 配置
    max_jobs = 10  # 最大并发任务数
    job_timeout = 3600  # 任务超时时间（秒）
    keep_result = 86400  # 保留任务结果时间（秒）
    
    # 重试配置
    max_tries = 3  # 最大重试次数
    retry_jobs = True  # 启用失败重试
