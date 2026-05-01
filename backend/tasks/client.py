"""
Arq 任务客户端

本模块提供任务提交和查询的客户端接口。
"""

import logging
import json
from typing import Any, Dict, Optional

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.jobs import Job, JobStatus

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
    
    async def submit_bundle_task(
        self,
        case_id: str,
        upload_path: str,
        upload_name: str,
    ) -> str:
        """提交压缩包解析任务（解压/分类/对齐一体化）。"""
        if not self._pool:
            await self.initialize()

        job = await self._pool.enqueue_job(
            "parse_bundle_task",
            case_id,
            upload_path,
            upload_name,
        )
        task_id = job.job_id
        # 初始化进度，前端可立即轮询
        await self._pool.set(
            f"task_progress:{task_id}",
            json.dumps({
                "percent": 5,
                "stage": "queued",
                "message": "任务已入队，等待处理",
            }, ensure_ascii=False),
            ex=3600,
        )
        logger.info(f"已提交压缩包解析任务: {task_id}, Case: {case_id}, File: {upload_name}")
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
        
        # arq >= 0.25：用 Job(job_id, redis)，ArqRedis 上无 get_job
        job = Job(task_id, self._pool)
        arq_st = await job.status()

        status_map: Dict[JobStatus, str] = {
            JobStatus.queued: "pending",
            JobStatus.deferred: "pending",
            JobStatus.in_progress: "running",
            JobStatus.complete: "completed",
            JobStatus.not_found: "not_found",
        }
        status = status_map.get(arq_st, "unknown")

        job_info = await job.info()
        result_info = await job.result_info()

        start_time = result_info.start_time if result_info else None
        finish_time = result_info.finish_time if result_info else None

        result: Dict[str, Any] = {
            "task_id": task_id,
            "status": status,
            "enqueue_time": job_info.enqueue_time.isoformat() if job_info and job_info.enqueue_time else None,
            "start_time": start_time.isoformat() if start_time else None,
            "finish_time": finish_time.isoformat() if finish_time else None,
        }
        progress_raw = await self._pool.get(f"task_progress:{task_id}")
        if progress_raw:
            try:
                if isinstance(progress_raw, bytes):
                    progress_raw = progress_raw.decode("utf-8")
                result["progress"] = json.loads(progress_raw)
            except Exception:  # noqa: BLE001
                pass

        if arq_st == JobStatus.complete and result_info is not None:
            if result_info.success:
                result["result"] = result_info.result
            else:
                result["status"] = "failed"
                err = result_info.result
                result["error"] = str(err) if err is not None else "task failed"
        elif arq_st == JobStatus.complete:
            try:
                result["result"] = await job.result(timeout=5.0)
            except Exception as e:
                logger.error(f"获取任务结果失败 {task_id}: {str(e)}")
                result["error"] = str(e)

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
        
        job = Job(task_id, self._pool)
        if await job.status() == JobStatus.not_found:
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
