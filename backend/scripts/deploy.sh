#!/bin/bash
# ============================================================
# FOTA 智能诊断平台 - Backend 部署脚本
# ============================================================
# 用途：生产环境部署 FastAPI Backend
# 使用：sudo ./scripts/deploy.sh

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}FOTA Backend 部署脚本${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 检查是否以 root 运行
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}错误: 请使用 sudo 运行此脚本${NC}"
    exit 1
fi

# 获取脚本所在目录的上一级（backend 目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
DEPLOY_DIR="/opt/fota-backend"

echo -e "${BLUE}配置信息:${NC}"
echo -e "  - Backend 源目录: $BACKEND_DIR"
echo -e "  - 部署目标目录: $DEPLOY_DIR"
echo ""

# 1. 检查并自动安装系统基础依赖
echo -e "${BLUE}[1/8] 检查并自动安装系统环境级依赖 (Python, PostgreSQL, Redis)...${NC}"
# 更新 apt 缓存并安装基础包
if ! command -v python3 &> /dev/null || ! command -v psql &> /dev/null || ! command -v redis-server &> /dev/null; then
    echo -e "${YELLOW}检测到部分基础设施缺失，正在自动执行 apt install...${NC}"
    apt-get update -y
    apt-get install -y python3 python3-venv python3-pip postgresql postgresql-contrib redis-server
fi

# 启动并使能底层数据库/缓存服务
systemctl enable --now redis-server
systemctl enable --now postgresql

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo -e "${GREEN}✓ 基础环境已就绪 (Python版本: $PYTHON_VERSION, PostgreSQL与Redis已配置)${NC}"

# 2. 创建专用系统用户
echo -e "${BLUE}[2/8] 创建系统用户...${NC}"
if ! id "fota" &>/dev/null; then
    useradd -r -s /sbin/nologin -d $DEPLOY_DIR fota
    echo -e "${GREEN}✓ 系统用户 'fota' 已创建${NC}"
else
    echo -e "${YELLOW}⚠ 系统用户 'fota' 已存在${NC}"
fi

# 3. 创建部署目录
echo -e "${BLUE}[3/8] 创建部署目录...${NC}"
mkdir -p $DEPLOY_DIR/{logs,data}
echo -e "${GREEN}✓ 部署目录已创建${NC}"

# 4. 复制代码到部署目录
echo -e "${BLUE}[4/8] 复制代码文件...${NC}"
rsync -av --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' \
    $BACKEND_DIR/ $DEPLOY_DIR/
chown -R fota:fota $DEPLOY_DIR
echo -e "${GREEN}✓ 代码文件已复制并设置权限${NC}"

# 5. 创建 Python 虚拟环境并安装依赖
echo -e "${BLUE}[5/8] 配置 Python 虚拟环境...${NC}"
if [ ! -d "$DEPLOY_DIR/venv" ]; then
    sudo -u fota python3 -m venv $DEPLOY_DIR/venv
    echo -e "${GREEN}✓ 虚拟环境已创建${NC}"
fi

echo -e "${BLUE}安装 Python 依赖...${NC}"
sudo -u fota $DEPLOY_DIR/venv/bin/pip install --upgrade pip
sudo -u fota $DEPLOY_DIR/venv/bin/pip install -r $DEPLOY_DIR/requirements.txt
echo -e "${GREEN}✓ Python 依赖已安装${NC}"

# 6. 配置环境变量
echo -e "${BLUE}[6/8] 配置环境变量...${NC}"
if [ ! -f "$DEPLOY_DIR/.env" ]; then
    if [ -f "$DEPLOY_DIR/.env.example" ]; then
        cp $DEPLOY_DIR/.env.example $DEPLOY_DIR/.env
        echo -e "${YELLOW}⚠ 已从 .env.example 创建 .env 文件${NC}"
        echo -e "${YELLOW}⚠ 请编辑 $DEPLOY_DIR/.env 填入真实配置${NC}"
    else
        echo -e "${RED}错误: .env.example 文件不存在${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠ .env 文件已存在，跳过创建${NC}"
fi

chmod 600 $DEPLOY_DIR/.env
chown fota:fota $DEPLOY_DIR/.env

# 7. 初始化业务库表结构 (Schema)
echo -e "${BLUE}[7/8] 初始化业务数据库表结构...${NC}"
# 执行原生 SQL 实例初始化 (包含创建初始账号和关联数据库主壳)
if [ -f "$BACKEND_DIR/scripts/init_postgres.sh" ]; then
    bash "$BACKEND_DIR/scripts/init_postgres.sh"
fi

# 利用 try...except 防止因为数据库未运行引发报错断融（容错机制）
sudo -u fota sh -c "cd $DEPLOY_DIR && venv/bin/python -c '
try:
    from database import db_manager
    db_manager.initialize()
    db_manager.create_tables()
    print(\"✓ 业务库表结构生成完毕。\")
except Exception as e:
    print(f\"⚠️ 暂无法连接数据库建表。请确保 PostgreSQL 服务运转正常，若刚部署请修改好 .env 后手动重试。\")
'" || true

# 8. 安装 systemd 服务
echo -e "${BLUE}[8/8] 安装 systemd 服务...${NC}"
if [ -f "$BACKEND_DIR/systemd/fota-backend.service" ]; then
    cp $BACKEND_DIR/systemd/fota-backend.service /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable fota-backend
    echo -e "${GREEN}✓ systemd 服务已安装并启用${NC}"
else
    echo -e "${YELLOW}⚠ systemd 服务文件不存在，跳过安装${NC}"
fi

# 设置目录权限
chown -R fota:fota $DEPLOY_DIR

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}部署完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}下一步操作:${NC}"
echo -e "  1. 编辑配置文件: sudo nano $DEPLOY_DIR/.env"
echo -e "  2. 启动服务: sudo systemctl start fota-backend"
echo -e "  3. 查看状态: sudo systemctl status fota-backend"
echo -e "  4. 查看日志: journalctl -u fota-backend -f"
echo ""
echo -e "${YELLOW}注意: 如需配置 Nginx 反向代理，请参考 nginx/backend.conf${NC}"
echo ""
