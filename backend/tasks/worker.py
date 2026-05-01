"""
Arq Worker 配置和任务定义

异步执行 log_pipeline 的 bundle 摄取（解压 → 分类 → 解码 → 预扫描 → 对齐 → 持久化）。
进度同步回 Redis 的 ``task_progress:{task_id}`` 键，供前端轮询。
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from uuid import UUID

from arq import cron
from arq.connections import RedisSettings

from config import settings
from log_pipeline.api.http import build_pipeline
from log_pipeline.config import Settings as PipelineSettings
from log_pipeline.interfaces import BundleStatus

logger = logging.getLogger(__name__)


def _set_task_progress_sync(redis, task_id: str, percent: int, stage: str, message: str) -> None:
    """Synchronous wrapper used from inside a thread (asyncio.run_coroutine_threadsafe)."""
    if not redis or not task_id:
        return
    payload = json.dumps(
        {"percent": percent, "stage": stage, "message": message},
        ensure_ascii=False,
    )
    coro = redis.set(f"task_progress:{task_id}", payload, ex=3600)
    try:
        asyncio.run_coroutine_threadsafe(coro, asyncio.get_event_loop()).result(timeout=2)
    except Exception:  # noqa: BLE001
        # progress reporting failures must never crash a long-running ingest
        pass


async def _set_task_progress(ctx, task_id: str, percent: int, stage: str, message: str) -> None:
    redis = ctx.get("redis")
    if not redis or not task_id:
        return
    payload = json.dumps(
        {"percent": percent, "stage": stage, "message": message},
        ensure_ascii=False,
    )
    await redis.set(f"task_progress:{task_id}", payload, ex=3600)


_STATUS_TO_PCT = {
    BundleStatus.QUEUED: 5,
    BundleStatus.EXTRACTING: 10,
    BundleStatus.DECODING: 40,
    BundleStatus.PRESCANNING: 70,
    BundleStatus.ALIGNING: 90,
    BundleStatus.DONE: 100,
    BundleStatus.FAILED: 100,
}


async def parse_bundle_task(
    ctx,
    case_id: str,
    upload_path: str,
    upload_name: str,
) -> dict:
    """压缩包摄取任务 — 委托给 log_pipeline.IngestPipeline.

    ``case_id`` 仅用于审计日志/进度消息；不再写 PostgreSQL（log_pipeline 自管 SQLite catalog）。
    """
    task_id = ctx.get("job_id", "")
    redis = ctx.get("redis")
    await _set_task_progress(ctx, task_id, 5, "preparing", "开始处理上传包")

    pipeline_settings = PipelineSettings.from_env()
    pipeline = build_pipeline(pipeline_settings)

    try:
        # register_upload + run 都是同步方法（CPU/IO 密集）；用 to_thread 让出 event loop
        bundle_id = await asyncio.to_thread(
            pipeline.register_upload, Path(upload_path), upload_name
        )
        await _set_task_progress(
            ctx, task_id, 10, "extracting",
            f"开始解析 bundle={bundle_id} case_id={case_id}",
        )

        # 起一个轮询 task：定期把 catalog 中的 progress 同步到 Redis
        async def _poll_progress() -> None:
            while True:
                await asyncio.sleep(1.0)
                try:
                    bundle = pipeline._catalog.get_bundle(bundle_id)
                    if bundle is None:
                        continue
                    status_str = bundle["status"]
                    progress = bundle.get("progress") or 0.0
                    percent = int(progress * 100)
                    await _set_task_progress(ctx, task_id, percent, status_str, "处理中")
                    if status_str in (BundleStatus.DONE.value, BundleStatus.FAILED.value):
                        return
                except Exception:  # noqa: BLE001
                    pass

        poll_task = asyncio.create_task(_poll_progress())

        try:
            result = await asyncio.to_thread(pipeline.run, bundle_id, Path(upload_path))
        finally:
            poll_task.cancel()
            try:
                await poll_task
            except (asyncio.CancelledError, Exception):
                pass

        bundle_row = pipeline._catalog.get_bundle(bundle_id)
        await _set_task_progress(ctx, task_id, 100, "completed", "处理完成")

        return {
            "case_id": case_id,
            "bundle_id": str(bundle_id),
            "uploaded_file": upload_name,
            "status": "completed" if bundle_row and bundle_row["status"] == "done" else "partial_success",
            "total_files": result.get("total_files", 0),
            "dedup_skipped": result.get("dedup_skipped", 0),
            "per_controller": result.get("per_controller", {}),
            "decode_counts": result.get("decode_counts", {}),
            "prescan_counts": result.get("prescan_counts", {}),
            "alignment": result.get("alignment", {}),
        }

    except Exception as e:
        await _set_task_progress(ctx, task_id, 100, "failed", f"处理失败: {e}")
        logger.error("bundle ingest failed - case=%s err=%s", case_id, e, exc_info=True)
        return {"case_id": case_id, "status": "failed", "error": str(e)}
    finally:
        # 上传文件已被 pipeline.run 删除，但兜底再清一次
        try:
            Path(upload_path).unlink(missing_ok=True)
        except OSError:
            pass


async def cleanup_old_tasks(ctx):
    """定时清理（占位）。"""
    logger.info("cleanup tick")
    return {"cleaned": 0}


class WorkerSettings:
    """Arq Worker 配置。"""
    redis_settings = RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
    )
    functions = [parse_bundle_task]
    cron_jobs = [cron(cleanup_old_tasks, hour=2, minute=0)]
    max_jobs = 10
    job_timeout = 3600
    keep_result = 86400
    max_tries = 3
    retry_jobs = True
