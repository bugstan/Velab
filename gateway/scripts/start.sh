#!/bin/bash
# ============================================================
# FOTA 智能诊断平台 - LiteLLM Gateway 启动脚本
# ============================================================
# 用途：开发环境快速启动，生产环境请使用 systemd
# 使用：chmod +x scripts/start.sh && ./scripts/start.sh

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}FOTA LiteLLM Gateway 启动脚本${NC}"
echo -e "${GREEN}========================================${NC}"

# 检查当前目录
if [ ! -f "config.yaml" ]; then
    echo -e "${RED}错误: 请在 gateway 目录下运行此脚本${NC}"
    exit 1
fi

# 检查 .env 文件
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}警告: .env 文件不存在${NC}"
    echo -e "${YELLOW}请复制 .env.example 为 .env 并填入真实配置${NC}"
    echo -e "${YELLOW}cp .env.example .env${NC}"
    exit 1
fi

# 检查 LiteLLM 是否安装
if ! command -v litellm &> /dev/null; then
    echo -e "${RED}错误: LiteLLM 未安装${NC}"
    echo -e "${YELLOW}请运行: pip install 'litellm[proxy]'${NC}"
    exit 1
fi

# 检查必需的环境变量
source .env
if [ -z "$LITELLM_MASTER_KEY" ]; then
    echo -e "${RED}错误: LITELLM_MASTER_KEY 未设置${NC}"
    exit 1
fi

if [ -z "$ANTHROPIC_API_KEY" ] && [ -z "$OPENAI_API_KEY" ]; then
    echo -e "${RED}错误: 至少需要配置一个 LLM API Key${NC}"
    exit 1
fi

# 创建日志目录
mkdir -p logs

# 显示配置信息
echo -e "${GREEN}配置检查通过${NC}"
echo -e "  - LiteLLM 版本: $(litellm --version)"
echo -e "  - 配置文件: config.yaml"
echo -e "  - 监听地址: ${HOST:-127.0.0.1}:${PORT:-4000}"
echo ""

# 启动服务
echo -e "${GREEN}正在启动 LiteLLM Gateway...${NC}"
echo -e "${YELLOW}按 Ctrl+C 停止服务${NC}"
echo ""

litellm \
    --config config.yaml \
    --host ${HOST:-127.0.0.1} \
    --port ${PORT:-4000} \
    --num_workers 4
