#!/bin/bash
# ============================================================
# FOTA 智能诊断平台 - 单机开发环境一键部署脚本
# ============================================================
# 用途：在单台服务器上快速部署 Backend + Gateway（仅用于开发/测试）
# 生产环境请使用各组件独立的部署脚本
# 使用：sudo ./scripts/deploy-all.sh

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}FOTA 单机开发环境一键部署${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}⚠️  警告: 此脚本仅用于单机开发/测试环境${NC}"
echo -e "${YELLOW}⚠️  生产环境请使用各组件独立的部署脚本${NC}"
echo ""

# 检查是否以 root 运行
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}错误: 请使用 sudo 运行此脚本${NC}"
    exit 1
fi

# 获取项目根目录
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
GATEWAY_DIR="$PROJECT_DIR/gateway"

echo -e "${BLUE}项目目录: $PROJECT_DIR${NC}"
echo ""

# 询问部署模式
echo -e "${BLUE}请选择部署模式:${NC}"
echo -e "  ${GREEN}A${NC} - 场景 A（平台在国内，需要 Gateway 中转）"
echo -e "  ${GREEN}B${NC} - 场景 B（平台在海外，直连 LLM API）"
echo ""
read -p "请输入选择 (A/B): " DEPLOYMENT_MODE

if [[ ! "$DEPLOYMENT_MODE" =~ ^[AaBb]$ ]]; then
    echo -e "${RED}错误: 无效的选择${NC}"
    exit 1
fi

DEPLOYMENT_MODE=$(echo "$DEPLOYMENT_MODE" | tr '[:lower:]' '[:upper:]')
echo -e "${GREEN}✓ 已选择场景 $DEPLOYMENT_MODE${NC}"
echo ""

# 1. 检查依赖
echo -e "${BLUE}[1/4] 检查系统依赖...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: Python3 未安装${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python3 已安装${NC}"

# 2. 部署 Backend
echo -e "${BLUE}[2/4] 部署 Backend...${NC}"
if [ -f "$BACKEND_DIR/scripts/deploy.sh" ]; then
    cd "$BACKEND_DIR"
    bash scripts/deploy.sh
    echo -e "${GREEN}✓ Backend 部署完成${NC}"
else
    echo -e "${RED}错误: Backend 部署脚本不存在${NC}"
    exit 1
fi

# 3. 部署 Gateway（仅场景 A）
if [ "$DEPLOYMENT_MODE" = "A" ]; then
    echo -e "${BLUE}[3/4] 部署 Gateway...${NC}"
    if [ -f "$GATEWAY_DIR/scripts/deploy.sh" ]; then
        cd "$GATEWAY_DIR"
        bash scripts/deploy.sh
        echo -e "${GREEN}✓ Gateway 部署完成${NC}"
    else
        echo -e "${RED}错误: Gateway 部署脚本不存在${NC}"
        exit 1
    fi
else
    echo -e "${BLUE}[3/4] 跳过 Gateway 部署（场景 B 不需要）${NC}"
fi

# 4. 配置部署模式
echo -e "${BLUE}[4/4] 配置部署模式...${NC}"
if [ -f "/opt/fota-backend/.env" ]; then
    sed -i "s/^DEPLOYMENT_MODE=.*/DEPLOYMENT_MODE=$DEPLOYMENT_MODE/" /opt/fota-backend/.env
    echo -e "${GREEN}✓ Backend 部署模式已设置为 $DEPLOYMENT_MODE${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}部署完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

if [ "$DEPLOYMENT_MODE" = "A" ]; then
    echo -e "${BLUE}场景 A 部署完成，下一步操作:${NC}"
    echo ""
    echo -e "${YELLOW}1. 配置 Gateway (LiteLLM):${NC}"
    echo -e "   sudo nano /opt/litellm-proxy/.env"
    echo -e "   ${YELLOW}填入真实的 API Keys${NC}"
    echo ""
    echo -e "${YELLOW}2. 配置 Backend:${NC}"
    echo -e "   sudo nano /opt/fota-backend/.env"
    echo -e "   ${YELLOW}设置 LITELLM_BASE_URL 指向 Gateway${NC}"
    echo ""
    echo -e "${YELLOW}3. 启动服务:${NC}"
    echo -e "   sudo systemctl start litellm"
    echo -e "   sudo systemctl start fota-backend"
    echo ""
    echo -e "${YELLOW}4. 检查状态:${NC}"
    echo -e "   sudo systemctl status litellm"
    echo -e "   sudo systemctl status fota-backend"
else
    echo -e "${BLUE}场景 B 部署完成，下一步操作:${NC}"
    echo ""
    echo -e "${YELLOW}1. 配置 Backend:${NC}"
    echo -e "   sudo nano /opt/fota-backend/.env"
    echo -e "   ${YELLOW}填入真实的 ANTHROPIC_API_KEY 和 OPENAI_API_KEY${NC}"
    echo ""
    echo -e "${YELLOW}2. 启动服务:${NC}"
    echo -e "   sudo systemctl start fota-backend"
    echo ""
    echo -e "${YELLOW}3. 检查状态:${NC}"
    echo -e "   sudo systemctl status fota-backend"
fi

echo ""
echo -e "${YELLOW}注意: 如需配置 Nginx 反向代理，请参考各组件的 nginx 目录${NC}"
echo ""
