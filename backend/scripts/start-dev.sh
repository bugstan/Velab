#!/bin/bash
# ============================================================
# FOTA 智能诊断平台 - Backend 开发环境启动脚本
# ============================================================
# 用途：开发环境快速启动 FastAPI Backend
# 使用：在 backend 目录: chmod +x scripts/start-dev.sh && ./scripts/start-dev.sh
# 虚拟环境：macOS 常见 .venv，Linux 常见 venv；已存在者优先。可用环境变量 VELAB_VENV_DIR 覆盖

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"
velab_path_prepend_brew
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}FOTA Backend 开发环境启动${NC}"
echo -e "${GREEN}========================================${NC}"
velab_print_os_hint
echo ""

# 检查 backend 根目录
if [ ! -f "$BACKEND_DIR/main.py" ]; then
    echo -e "${RED}错误: 请在项目 backend 目录下执行: ./scripts/start-dev.sh${NC}"
    exit 1
fi
cd "$BACKEND_DIR" || exit 1

# 检查 .env 文件
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}警告: .env 文件不存在${NC}"
    echo -e "${YELLOW}请复制 .env.example 为 .env 并填入真实配置${NC}"
    echo -e "${YELLOW}cp .env.example .env${NC}"
    exit 1
fi

velab_bootstrap_venv "$BACKEND_DIR"
# 若显式 VELAB_VENV_DIR 未设且两目录均不存在，create 的目录名与 velab_resolve_venv_dir 一致
if [ ! -d "$VELAB_VENV_DIR" ] || [ ! -f "$VELAB_VENV_DIR/bin/activate" ]; then
    echo -e "${YELLOW}虚拟环境不存在，正在创建: $VELAB_VENV_DIR${NC}"
    python3 -m venv "$VELAB_VENV_DIR"
    echo -e "${GREEN}✓ 虚拟环境已创建${NC}"
fi

# 激活虚拟环境并安装依赖
echo -e "${GREEN}安装/更新依赖...（$VELAB_VENV_DIR）${NC}"
# shellcheck source=/dev/null
source "$VELAB_VENV_DIR/bin/activate"
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
