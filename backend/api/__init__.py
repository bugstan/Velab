"""
FOTA诊断平台 - API模块

提供RESTful API接口用于:
- 案例管理
- 日志文件上传
- 解析任务提交和查询
- 事件查询和导出
- 诊断反馈与确认
"""

from fastapi import APIRouter

from .cases import router as cases_router
from .logs import router as logs_router
from .parse import router as parse_router
from .events import router as events_router
from .feedback import router as feedback_router
from .metrics import router as metrics_router

# 创建API路由器
api_router = APIRouter(prefix="/api")

# 注册子路由
api_router.include_router(cases_router, prefix="/cases", tags=["cases"])
api_router.include_router(logs_router, prefix="/logs", tags=["logs"])
api_router.include_router(parse_router, prefix="/parse", tags=["parse"])
api_router.include_router(events_router, prefix="/events", tags=["events"])
api_router.include_router(feedback_router, prefix="/feedback", tags=["feedback"])
api_router.include_router(metrics_router, prefix="", tags=["metrics"])

__all__ = ["api_router"]

