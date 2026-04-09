#!/bin/bash
# ============================================================
# FOTA 智能诊断平台 - Web 前端部署脚本
# ============================================================
# 用途：在生产服务器上自动安装、构建并配置 Next.js 前端服务
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}FOTA Web 前端部署脚本${NC}"
echo -e "${GREEN}========================================${NC}"

if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}错误: 请使用 sudo 运行此脚本${NC}"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$(dirname "$SCRIPT_DIR")"
DEPLOY_DIR="/opt/fota-web"

echo -e "${BLUE}[1/7] 检查并自动安装 Node.js 与 npm 依赖...${NC}"
if ! command -v npm &> /dev/null; then
    echo -e "${YELLOW}检测到未安装 npm/Node.js，正在通过 apt 安装...${NC}"
    apt-get update -y
    apt-get install -y nodejs npm
fi

echo -e "${BLUE}[2/7] 创建前端专用系统用户...${NC}"
if ! id "fota-web" &>/dev/null; then
    useradd -r -s /sbin/nologin -d $DEPLOY_DIR fota-web
    echo -e "${GREEN}✓ 系统用户 'fota-web' 已创建${NC}"
else
    echo -e "${YELLOW}⚠ 系统用户 'fota-web' 已存在${NC}"
fi

echo -e "${BLUE}[3/7] 创建前端部署目录...${NC}"
mkdir -p $DEPLOY_DIR
chown -R fota-web:fota-web $DEPLOY_DIR
echo -e "${GREEN}✓ 部署目录 $DEPLOY_DIR 已就绪${NC}"

echo -e "${BLUE}[4/7] 迁移与同步代码文件...${NC}"
# 同步前排除本地的 node_modules 和构建缓存
rsync -av --exclude='node_modules' --exclude='.next' $WEB_DIR/ $DEPLOY_DIR/
chown -R fota-web:fota-web $DEPLOY_DIR
echo -e "${GREEN}✓ 代码迁移完成并设置权限${NC}"

echo -e "${BLUE}[5/7] 配置生产环境变量...${NC}"
if [ ! -f "$DEPLOY_DIR/.env.local" ]; then
    if [ -f "$DEPLOY_DIR/.env.example" ]; then
        cp $DEPLOY_DIR/.env.example $DEPLOY_DIR/.env.local
    else
        echo "NEXT_PUBLIC_BACKEND_URL=http://localhost:8000" > $DEPLOY_DIR/.env.local
        echo "BACKEND_URL=http://localhost:8000" >> $DEPLOY_DIR/.env.local
    fi
    echo -e "${YELLOW}已为您初始化默认 .env.local 补齐跨域依赖${NC}"
else
    echo -e "${YELLOW}⚠ .env.local 已存在，跳过覆盖${NC}"
fi
chown fota-web:fota-web $DEPLOY_DIR/.env.local

echo -e "${BLUE}[6/7] 执行 NPM 安装与编译 (Next.js Build)...${NC}"
# 注意必须切到执行目录，并在用户赋权下进行构建
cd $DEPLOY_DIR
sudo -u fota-web npm install
sudo -u fota-web npm run build
echo -e "${GREEN}✓ 构建 (Build) 阶段成功完结${NC}"

echo -e "${BLUE}[7/7] 安装与挂载 systemd 服务...${NC}"
if [ -f "$WEB_DIR/systemd/fota-web.service" ]; then
    cp $WEB_DIR/systemd/fota-web.service /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable fota-web
    echo -e "${GREEN}✓ front-end systemd 服务已挂载并设置为开机自启${NC}"
else
    echo -e "${RED}无法找到 web/systemd/fota-web.service 服务描述文件${NC}"
fi

# 最后做一次防御性属主修补，防止 build 过程写出越权文件
chown -R fota-web:fota-web $DEPLOY_DIR

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Web 端子系统部署闭环完成！${NC}"
echo -e "${GREEN}当前应用端口: 3000${NC}"
echo -e "${GREEN}快速启动: sudo systemctl start fota-web${NC}"
echo -e "${GREEN}日志查看: sudo journalctl -u fota-web -f${NC}"
echo -e "${GREEN}========================================${NC}"
