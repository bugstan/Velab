"""
批量数据库操作模块

提供高性能的批量插入、更新和查询功能
"""

from typing import List, Dict, Any, Type, TypeVar, Optional
from datetime import datetime
import logging

from sqlalchemy import insert, update, select
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.models.base import Base
from backend.models.event import DiagnosisEvent
from backend.models.log_file import RawLogFile, ParseStatus

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=Base)


class BatchOperations:
    """
    批量操作工具类
    
    提供高性能的批量插入、更新功能,特别优化了大量事件的插入场景
    """
    
    @staticmethod
    def bulk_insert_events(
        session: Session,
        events: List[Dict[str, Any]],
        batch_size: int = 1000
    ) -> int:
        """
        批量插入诊断事件(同步)
        
        使用PostgreSQL的COPY或批量INSERT优化性能
        
        Args:
            session: 数据库会话
            events: 事件字典列表
            batch_size: 每批次大小
        
        Returns:
            int: 插入的事件数量
        """
        if not events:
            return 0
        
        total_inserted = 0
        
        try:
            # 分批插入
            for i in range(0, len(events), batch_size):
                batch = events[i:i + batch_size]
                
                # 使用bulk_insert_mappings提高性能
                session.bulk_insert_mappings(DiagnosisEvent, batch)
                total_inserted += len(batch)
                
                logger.debug(f"批量插入事件: {len(batch)}条 (总计: {total_inserted}/{len(events)})")
            
            session.commit()
            logger.info(f"成功批量插入 {total_inserted} 条诊断事件")
            
        except Exception as e:
            session.rollback()
            logger.error(f"批量插入事件失败: {e}")
            raise
        
        return total_inserted
    
    @staticmethod
    async def bulk_insert_events_async(
        session: AsyncSession,
        events: List[Dict[str, Any]],
        batch_size: int = 1000
    ) -> int:
        """
        批量插入诊断事件(异步)
        
        Args:
            session: 异步数据库会话
            events: 事件字典列表
            batch_size: 每批次大小
        
        Returns:
            int: 插入的事件数量
        """
        if not events:
            return 0
        
        total_inserted = 0
        
        try:
            # 分批插入
            for i in range(0, len(events), batch_size):
                batch = events[i:i + batch_size]
                
                # 使用INSERT语句
                stmt = insert(DiagnosisEvent).values(batch)
                await session.execute(stmt)
                total_inserted += len(batch)
                
                logger.debug(f"批量插入事件: {len(batch)}条 (总计: {total_inserted}/{len(events)})")
            
            await session.commit()
            logger.info(f"成功批量插入 {total_inserted} 条诊断事件(异步)")
            
        except Exception as e:
            await session.rollback()
            logger.error(f"批量插入事件失败(异步): {e}")
            raise
        
        return total_inserted
    
    @staticmethod
    def upsert_events(
        session: Session,
        events: List[Dict[str, Any]],
        batch_size: int = 1000
    ) -> int:
        """
        批量插入或更新事件(UPSERT)
        
        使用PostgreSQL的ON CONFLICT DO UPDATE实现幂等性
        
        Args:
            session: 数据库会话
            events: 事件字典列表
            batch_size: 每批次大小
        
        Returns:
            int: 处理的事件数量
        """
        if not events:
            return 0
        
        total_processed = 0
        
        try:
            for i in range(0, len(events), batch_size):
                batch = events[i:i + batch_size]
                
                # PostgreSQL UPSERT
                stmt = pg_insert(DiagnosisEvent).values(batch)
                stmt = stmt.on_conflict_do_update(
                    constraint='diagnosis_events_case_file_idx',
                    set_={
                        'message': stmt.excluded.message,
                        'event_type': stmt.excluded.event_type,
                        'level': stmt.excluded.level,
                        'normalized_ts': stmt.excluded.normalized_ts,
                        'parsed_fields': stmt.excluded.parsed_fields,
                    }
                )
                
                session.execute(stmt)
                total_processed += len(batch)
                
                logger.debug(f"UPSERT事件: {len(batch)}条 (总计: {total_processed}/{len(events)})")
            
            session.commit()
            logger.info(f"成功UPSERT {total_processed} 条诊断事件")
            
        except Exception as e:
            session.rollback()
            logger.error(f"UPSERT事件失败: {e}")
            raise
        
        return total_processed
    
    @staticmethod
    def update_file_parse_status(
        session: Session,
        file_id: str,
        status: ParseStatus,
        error: Optional[str] = None
    ):
        """
        更新文件解析状态
        
        Args:
            session: 数据库会话
            file_id: 文件ID
            status: 解析状态
            error: 错误信息(可选)
        """
        try:
            update_data = {
                'parse_status': status.value,
            }
            
            if status == ParseStatus.PARSING:
                update_data['parse_started_at'] = datetime.utcnow()
            elif status == ParseStatus.PARSED:
                update_data['parse_completed_at'] = datetime.utcnow()
            elif status == ParseStatus.FAILED:
                update_data['parse_completed_at'] = datetime.utcnow()
                update_data['parse_error'] = error
            
            stmt = (
                update(RawLogFile)
                .where(RawLogFile.file_id == file_id)
                .values(**update_data)
            )
            
            session.execute(stmt)
            session.commit()
            
            logger.info(f"更新文件解析状态: file_id={file_id}, status={status.value}")
            
        except Exception as e:
            session.rollback()
            logger.error(f"更新文件解析状态失败: {e}")
            raise
    
    @staticmethod
    async def update_file_parse_status_async(
        session: AsyncSession,
        file_id: str,
        status: ParseStatus,
        error: Optional[str] = None
    ):
        """
        更新文件解析状态(异步)
        
        Args:
            session: 异步数据库会话
            file_id: 文件ID
            status: 解析状态
            error: 错误信息(可选)
        """
        try:
            update_data = {
                'parse_status': status.value,
            }
            
            if status == ParseStatus.PARSING:
                update_data['parse_started_at'] = datetime.utcnow()
            elif status == ParseStatus.PARSED:
                update_data['parse_completed_at'] = datetime.utcnow()
            elif status == ParseStatus.FAILED:
                update_data['parse_completed_at'] = datetime.utcnow()
                update_data['parse_error'] = error
            
            stmt = (
                update(RawLogFile)
                .where(RawLogFile.file_id == file_id)
                .values(**update_data)
            )
            
            await session.execute(stmt)
            await session.commit()
            
            logger.info(f"更新文件解析状态(异步): file_id={file_id}, status={status.value}")
            
        except Exception as e:
            await session.rollback()
            logger.error(f"更新文件解析状态失败(异步): {e}")
            raise
    
    @staticmethod
    def get_events_by_case(
        session: Session,
        case_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[str]] = None,
        modules: Optional[List[str]] = None,
        limit: int = 1000,
        offset: int = 0
    ) -> List[DiagnosisEvent]:
        """
        查询案件的诊断事件
        
        Args:
            session: 数据库会话
            case_id: 案件ID
            start_time: 开始时间(可选)
            end_time: 结束时间(可选)
            event_types: 事件类型列表(可选)
            modules: 模块列表(可选)
            limit: 返回数量限制
            offset: 偏移量
        
        Returns:
            List[DiagnosisEvent]: 事件列表
        """
        query = session.query(DiagnosisEvent).filter(
            DiagnosisEvent.case_id == case_id
        )
        
        # 时间范围过滤
        if start_time:
            query = query.filter(DiagnosisEvent.normalized_ts >= start_time)
        if end_time:
            query = query.filter(DiagnosisEvent.normalized_ts <= end_time)
        
        # 事件类型过滤
        if event_types:
            query = query.filter(DiagnosisEvent.event_type.in_(event_types))
        
        # 模块过滤
        if modules:
            query = query.filter(DiagnosisEvent.module.in_(modules))
        
        # 排序和分页
        query = query.order_by(DiagnosisEvent.normalized_ts).limit(limit).offset(offset)
        
        return query.all()
    
    @staticmethod
    async def get_events_by_case_async(
        session: AsyncSession,
        case_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[str]] = None,
        modules: Optional[List[str]] = None,
        limit: int = 1000,
        offset: int = 0
    ) -> List[DiagnosisEvent]:
        """
        查询案件的诊断事件(异步)
        
        Args:
            session: 异步数据库会话
            case_id: 案件ID
            start_time: 开始时间(可选)
            end_time: 结束时间(可选)
            event_types: 事件类型列表(可选)
            modules: 模块列表(可选)
            limit: 返回数量限制
            offset: 偏移量
        
        Returns:
            List[DiagnosisEvent]: 事件列表
        """
        stmt = select(DiagnosisEvent).filter(
            DiagnosisEvent.case_id == case_id
        )
        
        # 时间范围过滤
        if start_time:
            stmt = stmt.filter(DiagnosisEvent.normalized_ts >= start_time)
        if end_time:
            stmt = stmt.filter(DiagnosisEvent.normalized_ts <= end_time)
        
        # 事件类型过滤
        if event_types:
            stmt = stmt.filter(DiagnosisEvent.event_type.in_(event_types))
        
        # 模块过滤
        if modules:
            stmt = stmt.filter(DiagnosisEvent.module.in_(modules))
        
        # 排序和分页
        stmt = stmt.order_by(DiagnosisEvent.normalized_ts).limit(limit).offset(offset)
        
        result = await session.execute(stmt)
        return result.scalars().all()
    
    @staticmethod
    def bulk_update_event_timestamps(
        session: Session,
        updates: List[Dict[str, Any]],
        batch_size: int = 1000
    ) -> int:
        """
        批量更新事件的normalized_ts
        
        Args:
            session: 数据库会话
            updates: 更新数据列表，每项包含 event_id 和 normalized_ts
            batch_size: 每批次大小
        
        Returns:
            int: 更新的事件数量
        """
        if not updates:
            return 0
        
        total_updated = 0
        
        try:
            for i in range(0, len(updates), batch_size):
                batch = updates[i:i + batch_size]
                
                # 使用bulk_update_mappings提高性能
                session.bulk_update_mappings(DiagnosisEvent, batch)
                total_updated += len(batch)
                
                logger.debug(f"批量更新时间戳: {len(batch)}条 (总计: {total_updated}/{len(updates)})")
            
            session.commit()
            logger.info(f"成功批量更新 {total_updated} 条事件时间戳")
            
        except Exception as e:
            session.rollback()
            logger.error(f"批量更新时间戳失败: {e}")
            raise
        
        return total_updated


# 便捷函数
def bulk_insert_events(
    session: Session,
    events: List[Dict[str, Any]],
    batch_size: int = 1000
) -> int:
    """批量插入事件(便捷函数)"""
    return BatchOperations.bulk_insert_events(session, events, batch_size)


async def bulk_insert_events_async(
    session: AsyncSession,
    events: List[Dict[str, Any]],
    batch_size: int = 1000
) -> int:
    """批量插入事件(异步便捷函数)"""
    return await BatchOperations.bulk_insert_events_async(session, events, batch_size)
