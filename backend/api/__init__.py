"""
FOTA诊断平台 - API模块

提供RESTful API接口用于:
- 案例管理（cases）
- 日志包上传/查询/事件检索（log_pipeline → /api/bundles/...）
- 诊断反馈（feedback）
"""

from fastapi import APIRouter

from .cases import router as cases_router
from .feedback import router as feedback_router
from log_pipeline.api.http import router as bundles_router, metrics_router

api_router = APIRouter(prefix="/api")

api_router.include_router(cases_router, prefix="/cases", tags=["cases"])
api_router.include_router(feedback_router, prefix="/feedback", tags=["feedback"])
# log_pipeline 的 router 已经声明 /bundles 前缀；挂在 /api 下即得 /api/bundles/*
api_router.include_router(bundles_router, tags=["bundles"])

__all__ = ["api_router", "metrics_router"]
