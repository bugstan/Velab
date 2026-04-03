#!/bin/bash
# ============================================================
# FOTA 智能诊断平台 - Backend 开发环境启动脚本
# ============================================================
# 用途：开发环境快速启动 FastAPI Backend
# 使用：chmod +x scripts/start-dev.sh && ./scripts/start-dev.sh

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}FOTA Backend 开发环境启动${NC}"
echo -e "${GREEN}========================================${NC}"

# 检查当前目录
if [ ! -f "main.py" ]; then
    echo -e "${RED}错误: 请在 backend 目录下运行此脚本${NC}"
    exit 1
fi

# 检查 .env 文件
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}警告: .env 文件不存在${NC}"
    echo -e "${YELLOW}请复制 .env.example 为 .env 并填入真实配置${NC}"
    echo -e "${YELLOW}cp .env.example .env${NC}"
    exit 1
fi

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}虚拟环境不存在，正在创建...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}✓ 虚拟环境已创建${NC}"
fi

# 激活虚拟环境并安装依赖
echo -e "${GREEN}安装/更新依赖...${NC}"
source venv/bin/activate
pip install --upgrade pip > /dev/null
pip install -r requirements.txt

# 检查必需的环境变量
source .env
if [ -z "$DEPLOYMENT_MODE" ]; then
    echo -e "${RED}错误: DEPLOYMENT_MODE 未设置${NC}"
    exit 1
fi

# 显示配置信息
echo -e "${GREEN}配置检查通过${NC}"
echo -e "  - Python 版本: $(python --version)"
echo -e "  - 部署模式: $DEPLOYMENT_MODE"
echo -e "  - 监听地址: 0.0.0.0:8000"
echo ""

# 启动服务
echo -e "${GREEN}正在启动 FOTA Backend...${NC}"
echo -e "${YELLOW}按 Ctrl+C 停止服务${NC}"
echo -e "${YELLOW}访问 http://localhost:8000/health 检查服务状态${NC}"
echo -e "${YELLOW}访问 http://localhost:8000/docs 查看 API 文档${NC}"
echo ""

python main.py
