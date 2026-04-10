"""
监控指标 API — Prometheus 格式指标导出

提供系统运行指标：
- 请求计数和延迟
- Agent 执行统计
- 缓存命中率
- 数据库连接池状态

作者：FOTA 诊断平台团队
创建时间：2026-04-06
"""

from __future__ import annotations

import time
import logging
from collections import defaultdict
from typing import Dict, Any

from fastapi import APIRouter, Request, Response

logger = logging.getLogger(__name__)

router = APIRouter()


class MetricsCollector:
    """
    指标收集器

    轻量级实现，不依赖 prometheus_client 库。
    导出 Prometheus text format。
    """

    def __init__(self):
        self._counters: Dict[str, int] = defaultdict(int)
        self._histograms: Dict[str, list] = defaultdict(list)
        self._gauges: Dict[str, float] = {}
        self._max_histogram_size = 1000  # 每个指标最多保留 1000 个样本

    def inc_counter(self, name: str, labels: str = "", value: int = 1):
        """递增计数器"""
        key = f"{name}{{{labels}}}" if labels else name
        self._counters[key] += value

    def observe_histogram(self, name: str, value: float, labels: str = ""):
        """记录直方图样本"""
        key = f"{name}{{{labels}}}" if labels else name
        samples = self._histograms[key]
        samples.append(value)
        if len(samples) > self._max_histogram_size:
            self._histograms[key] = samples[-self._max_histogram_size:]

    def set_gauge(self, name: str, value: float, labels: str = ""):
        """设置仪表盘值"""
        key = f"{name}{{{labels}}}" if labels else name
        self._gauges[key] = value

    def export_prometheus(self) -> str:
        """导出 Prometheus text format"""
        lines = []

        # Counters
        for key, value in sorted(self._counters.items()):
            lines.append(f"# TYPE {key.split('{')[0]} counter")
            lines.append(f"{key} {value}")

        # Gauges
        for key, value in sorted(self._gauges.items()):
            lines.append(f"# TYPE {key.split('{')[0]} gauge")
            lines.append(f"{key} {value}")

        # Histogram summaries
        for key, samples in sorted(self._histograms.items()):
            base_name = key.split("{")[0]
            if not samples:
                continue
            lines.append(f"# TYPE {base_name} summary")
            lines.append(f"{key}_count {len(samples)}")
            lines.append(f"{key}_sum {sum(samples):.3f}")
            sorted_samples = sorted(samples)
            n = len(sorted_samples)
            lines.append(f'{key}{{quantile="0.5"}} {sorted_samples[n // 2]:.3f}')
            lines.append(f'{key}{{quantile="0.9"}} {sorted_samples[int(n * 0.9)]:.3f}')
            lines.append(f'{key}{{quantile="0.99"}} {sorted_samples[min(int(n * 0.99), n - 1)]:.3f}')

        return "\n".join(lines) + "\n"

    def get_summary(self) -> Dict[str, Any]:
        """获取 JSON 格式摘要"""
        summary = {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {},
        }
        for key, samples in self._histograms.items():
            if samples:
                summary["histograms"][key] = {
                    "count": len(samples),
                    "avg": round(sum(samples) / len(samples), 3),
                    "p50": round(sorted(samples)[len(samples) // 2], 3),
                    "p99": round(sorted(samples)[min(int(len(samples) * 0.99), len(samples) - 1)], 3),
                }
        return summary


# 全局单例
metrics = MetricsCollector()


# ── API Endpoints ──


@router.get("/metrics")
def prometheus_metrics():
    """Prometheus 格式指标导出"""
    from database import db_manager

    # 更新数据库连接池指标
    try:
        pool_status = db_manager.get_pool_status()
        if "size" in pool_status:
            metrics.set_gauge("fota_db_pool_size", pool_status["size"])
            metrics.set_gauge("fota_db_pool_checked_out", pool_status.get("checked_out", 0))
            metrics.set_gauge("fota_db_pool_overflow", pool_status.get("overflow", 0))
    except Exception:
        pass

    content = metrics.export_prometheus()
    return Response(content=content, media_type="text/plain; charset=utf-8")


@router.get("/metrics/json")
def json_metrics():
    """JSON 格式指标摘要"""
    return metrics.get_summary()
