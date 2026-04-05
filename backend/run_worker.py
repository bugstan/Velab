#!/usr/bin/env python3
"""
Arq Worker 启动脚本

运行方式:
    python run_worker.py

或使用arq命令:
    arq tasks.worker.WorkerSettings
"""

import sys
import logging
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from arq import run_worker
from tasks.worker import WorkerSettings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """启动Arq Worker"""
    logger.info("启动 Arq Worker...")
    logger.info(f"Redis: {WorkerSettings.redis_settings.host}:{WorkerSettings.redis_settings.port}")
    logger.info(f"最大并发任务数: {WorkerSettings.max_jobs}")
    logger.info(f"任务超时时间: {WorkerSettings.job_timeout}秒")
    
    # 运行worker
    run_worker(WorkerSettings)


if __name__ == "__main__":
    main()
