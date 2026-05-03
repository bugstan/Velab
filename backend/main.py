"""
FOTA 智能诊断平台 — FastAPI 后端服务

本模块是诊断平台的 HTTP 服务入口，提供基于 SSE（Server-Sent Events）的
流式对话接口。主要功能包括：

1. /chat 端点：接收用户诊断请求，通过 SSE 流式返回分析结果
2. /health 端点：健康检查和 Agent 状态查询
3. 全链路日志追踪：每个请求分配唯一 trace_id
4. CORS 支持：允许前端跨域访问

技术栈：
- FastAPI: 异步 Web 框架
- SSE (Server-Sent Events): 实时流式响应
- sse-starlette: SSE 支持库

作者：FOTA 诊断平台团队
创建时间：2025
最后更新：2025
"""

from __future__ import annotations

import json
import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from common.chain_log import (
    bind_trace_id,
    chain_debug,
    new_trace_id,
    reset_trace_id,
    setup_logging,
)
from config import settings

from contextlib import asynccontextmanager

# 导入 Agent 模块，触发自动注册
# 这些导入语句会执行模块级代码，将 Agent 实例注册到全局 registry
import agents.log_analytics  # noqa: F401
import agents.jira_knowledge  # noqa: F401
import agents.doc_retrieval  # noqa: F401

from agents.orchestrator import orchestrate

# 导入API路由
from api import api_router

# 导入数据库管理器
from database import db_manager
from services.llm import log_llm_route_on_startup

# log_pipeline state 初始化函数（在 lifespan 中调用）
from log_pipeline.api.http import init_app_state as init_log_pipeline_state

# 初始化日志系统
setup_logging()

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时初始化，关闭时清理"""
    # ── Startup ──
    log.info("Initializing database connection pool...")
    db_manager.initialize()
    log.info("Database connection pool initialized")

    log.info("Creating database tables (if not exist)...")
    db_manager.create_tables()
    log.info("Database tables ready")

    log.info("Initializing task client...")
    from tasks.client import get_task_client
    await get_task_client()
    log.info("Task client initialized")

    log.info("Initializing log_pipeline state...")
    init_log_pipeline_state(app)
    log.info("log_pipeline state initialized")

    # 启动即打印最终 LLM 路由决策，便于排查是否走 gateway / 直连
    log_llm_route_on_startup()

    yield  # 应用运行中

    # ── Shutdown ──
    log.info("Closing task client...")
    from tasks.client import close_task_client
    await close_task_client()
    log.info("Task client closed")

    log.info("Closing database connections...")
    db_manager.close()
    log.info("Database connections closed")


# 创建 FastAPI 应用实例
app = FastAPI(
    title="FOTA 智能诊断平台",
    description="FOTA多域日志智能诊断系统 - 提供日志解析、时间对齐、事件查询等功能",
    version="1.0.0",
    lifespan=lifespan,
)

# 配置 CORS 中间件，允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS.split(","),  # 从环境变量读取，避免通配符
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册API路由
app.include_router(api_router)

# log_pipeline 的 Prometheus /metrics 端点（不带 /api 前缀）
from api import metrics_router  # noqa: E402
app.include_router(metrics_router)


@app.get("/")
async def root():
    """
    根路径 - API信息
    
    Returns:
        API基本信息和可用端点
    """
    return {
        "name": "FOTA 智能诊断平台",
        "version": "1.0.0",
        "endpoints": {
            "chat": "/chat - 诊断对话接口(SSE)",
            "health": "/health - 健康检查",
            "api": "/api - RESTful API接口",
            "docs": "/docs - API文档(Swagger UI)",
            "redoc": "/redoc - API文档(ReDoc)"
        }
    }


@app.post("/chat")
async def chat(request: Request):
    """
    诊断对话接口（SSE 流式响应）
    
    接收用户的诊断问题，通过 Orchestrator 编排多个 Agent 进行分析，
    并以 SSE 格式流式返回分析过程和最终结果。
    
    请求体格式：
    {
        "message": "用户的诊断问题",
        "scenarioId": "场景 ID（如 fota-diagnostic）",
        "history": [{"role": "user/assistant", "content": "..."}]  // 可选的对话历史
    }
    
    响应格式（SSE 事件流）：
    - step_start: Agent 开始执行
    - step_progress: Agent 执行进度更新
    - step_complete: Agent 执行完成
    - content_start: 开始生成最终回复
    - content_delta: 流式输出回复内容
    - content_complete: 回复生成完成
    - done: 整个流程结束
    
    Args:
        request: FastAPI Request 对象
    
    Returns:
        EventSourceResponse: SSE 流式响应
    """
    body = await request.json()
    user_message: str = body.get("message", "")
    scenario_id: str = body.get("scenarioId", "fota-diagnostic")
    history: list[dict] = body.get("history", [])
    bundle_id_raw: str | None = body.get("bundleId") or None

    # 在 API 边界验证 bundle_id 格式（防止路径注入 / SSRF）
    bundle_id: str | None = None
    if bundle_id_raw is not None:
        import re as _re
        if not _re.fullmatch(
            r"[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}",
            bundle_id_raw, _re.IGNORECASE
        ):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "bundleId must be a valid UUID"}, status_code=400)
        bundle_id = bundle_id_raw

    async def event_generator():
        """SSE 事件生成器，负责流式推送诊断过程"""
        # 为本次请求分配唯一的 trace_id，用于日志追踪
        trace_token = bind_trace_id(new_trace_id())
        t0 = time.perf_counter()
        chain_debug(
            log,
            step="http.chat",
            event="SSE_BEGIN",
            scenario_id=scenario_id,
            user_len=len(user_message),
            history_turns=len(history),
        )
        event_count = 0
        try:
            # 调用 Orchestrator 执行诊断流程，逐个 yield SSE 事件
            async for event in orchestrate(user_message, scenario_id, history, bundle_id):
                event_count += 1
                yield {"data": json.dumps(event, ensure_ascii=False)}
        finally:
            # 记录请求完成日志
            chain_debug(
                log,
                step="http.chat",
                event="SSE_END",
                elapsed_ms=(time.perf_counter() - t0) * 1000,
                events_emitted=event_count,
            )
            # 清理 trace_id 上下文
            reset_trace_id(trace_token)

    return EventSourceResponse(event_generator())


@app.get("/health")
async def health():
    """
    健康检查接口
    
    返回服务状态和已注册的 Agent 列表，用于监控和调试。
    
    Returns:
        dict: 包含 status 和 agents 列表的字典
            {
                "status": "ok",
                "agents": [
                    {"name": "log_analytics", "display_name": "Log Analytics Agent"},
                    ...
                ]
            }
    """
    from agents.base import registry
    agents = [{"name": a.name, "display_name": a.display_name} for a in registry.all_agents()]
    return {"status": "ok", "agents": agents}


if __name__ == "__main__":
    import uvicorn

    # 开发模式：启用热重载
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
