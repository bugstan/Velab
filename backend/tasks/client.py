"""
Arq 任务客户端

本模块提供任务提交和查询的客户端接口。
"""

import logging
from typing import Optional

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from config import settings

logger = logging.getLogger(__name__)


class TaskClient:
    """
    异步任务客户端
    
    提供任务提交、查询、取消等操作的封装接口。
    """
    
    def __init__(self):
        """初始化任务客户端"""
        self._pool: Optional[ArqRedis] = None
        self._redis_settings = RedisSettings(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
        )
    
    async def initialize(self):
        """初始化 Redis 连接池"""
        if self._pool is None:
            self._pool = await create_pool(self._redis_settings)
            logger.info("任务客户端已初始化")
    
    async def close(self):
        """关闭 Redis 连接池"""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("任务客户端已关闭")
    
    async def submit_parse_task(
        self,
        case_id: str,
        file_ids: list[str],
        time_window_start: Optional[str] = None,
        time_window_end: Optional[str] = None,
        max_lines_per_file: Optional[int] = None,
    ) -> str:
        """
        提交日志解析任务
        
        Args:
            case_id: 案例ID
            file_ids: 待解析的日志文件ID列表
            time_window_start: 时间窗口起始（ISO格式）
            time_window_end: 时间窗口结束（ISO格式）
            max_lines_per_file: 每个文件最大解析行数
        
        Returns:
            str: 任务ID
        """
        if not self._pool:
            await self.initialize()
        
        job = await self._pool.enqueue_job(
            "parse_logs_task",
            case_id,
            file_ids,
            time_window_start,
            time_window_end,
            max_lines_per_file,
        )
        
        task_id = job.job_id
        logger.info(f"已提交解析任务: {task_id}, Case: {case_id}, Files: {len(file_ids)}")
        return task_id
    
    async def get_task_status(self, task_id: str) -> dict:
        """
        查询任务状态
        
        Args:
            task_id: 任务ID
        
        Returns:
            dict: 任务状态信息
        """
        if not self._pool:
            await self.initialize()
        
        job = await self._pool.get_job(task_id)
        
        if not job:
            return {
                "task_id": task_id,
                "status": "not_found",
                "message": "任务不存在或已过期",
            }
        
        # 获取任务信息
        job_info = await job.info()
        
        # 映射 Arq 状态到我们的状态
        status_map = {
            "queued": "pending",
            "in_progress": "running",
            "complete": "completed",
            "not_found": "not_found",
        }
        
        arq_status = job_info.status if job_info else "not_found"
        status = status_map.get(arq_status, "unknown")
        
        result = {
            "task_id": task_id,
            "status": status,
            "enqueue_time": job_info.enqueue_time.isoformat() if job_info and job_info.enqueue_time else None,
            "start_time": job_info.start_time.isoformat() if job_info and job_info.start_time else None,
            "finish_time": job_info.finish_time.isoformat() if job_info and job_info.finish_time else None,
        }
        
        # 如果任务完成，获取结果
        if status == "completed":
            try:
                task_result = await job.result()
                result["result"] = task_result
            except Exception as e:
                logger.error(f"获取任务结果失败 {task_id}: {str(e)}")
                result["error"] = str(e)
        
        # 如果任务失败，获取错误信息
        if job_info and job_info.result and isinstance(job_info.result, Exception):
            result["status"] = "failed"
            result["error"] = str(job_info.result)
        
        return result
    
    async def cancel_task(self, task_id: str) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务ID
        
        Returns:
            bool: 是否成功取消
        """
        if not self._pool:
            await self.initialize()
        
        job = await self._pool.get_job(task_id)
        
        if not job:
            logger.warning(f"任务不存在: {task_id}")
            return False
        
        try:
            await job.abort()
            logger.info(f"已取消任务: {task_id}")
            return True
        except Exception as e:
            logger.error(f"取消任务失败 {task_id}: {str(e)}")
            return False
    
    async def get_queue_info(self) -> dict:
        """
        获取队列信息
        
        Returns:
            dict: 队列统计信息
        """
        if not self._pool:
            await self.initialize()
        
        try:
            # 获取队列长度
            queue_length = await self._pool.zcard("arq:queue")
            
            return {
                "queue_length": queue_length,
                "redis_host": settings.REDIS_HOST,
                "redis_port": settings.REDIS_PORT,
            }
        except Exception as e:
            logger.error(f"获取队列信息失败: {str(e)}")
            return {
                "error": str(e),
            }


# 全局任务客户端实例
_task_client: Optional[TaskClient] = None


async def get_task_client() -> TaskClient:
    """
    获取全局任务客户端实例（依赖注入）
    
    Returns:
        TaskClient: 任务客户端实例
    """
    global _task_client
    if _task_client is None:
        _task_client = TaskClient()
        await _task_client.initialize()
    return _task_client


async def close_task_client():
    """关闭全局任务客户端"""
    global _task_client
    if _task_client:
        await _task_client.close()
        _task_client = None
