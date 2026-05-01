"""
FOTA 智能诊断平台 — 异步任务队列模块

本模块使用 Arq (基于 Redis) 实现异步任务队列，用于处理耗时的日志解析任务。

主要功能：
1. 异步日志解析任务
2. 任务状态跟踪
3. 失败重试机制
4. 分布式 Worker 支持

作者：FOTA 诊断平台团队
创建时间：2026-04-04
"""

from .worker import WorkerSettings, parse_bundle_task
from .client import TaskClient, get_task_client

__all__ = [
    "WorkerSettings",
    "parse_bundle_task",
    "TaskClient",
    "get_task_client",
]
