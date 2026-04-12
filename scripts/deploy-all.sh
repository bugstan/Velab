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
WEB_DIR="$PROJECT_DIR/web"

echo -e "${BLUE}项目目录: $PROJECT_DIR${NC}"
echo ""

# ── 命令行参数解析（支持非交互式 / CI 调用）──
# 用法: sudo ./scripts/deploy-all.sh [--mode A|B] [--domain DOMAIN]
DEPLOYMENT_MODE=""
SERVER_DOMAIN=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --mode|-m)
            DEPLOYMENT_MODE="$(echo "$2" | tr '[:lower:]' '[:upper:]')"
            shift 2
            ;;
        --domain|-d)
            SERVER_DOMAIN="$2"
            shift 2
            ;;
        --help|-h)
            echo "用法: $0 [--mode A|B] [--domain DOMAIN]"
            echo "  --mode,   -m   部署场景：A（国内 Gateway 中转）或 B（海外直连 LLM API）"
            echo "  --domain, -d   平台访问地址（域名或 IP，留空则交互式输入，默认 localhost）"
            exit 0
            ;;
        *)
            echo -e "${RED}错误: 未知参数 $1，使用 --help 查看用法${NC}"
            exit 1
            ;;
    esac
done

# 询问部署模式（仅当未通过 --mode 参数指定时）
if [ -z "$DEPLOYMENT_MODE" ]; then
    echo -e "${BLUE}请选择部署模式:${NC}"
    echo -e "  ${GREEN}A${NC} - 场景 A（平台在国内，需要 Gateway 中转）"
    echo -e "  ${GREEN}B${NC} - 场景 B（平台在海外，直连 LLM API）"
    echo ""
    read -p "请输入选择 (A/B): " DEPLOYMENT_MODE
fi

if [[ ! "$DEPLOYMENT_MODE" =~ ^[AaBb]$ ]]; then
    echo -e "${RED}错误: 无效的选择${NC}"
    exit 1
fi

DEPLOYMENT_MODE=$(echo "$DEPLOYMENT_MODE" | tr '[:lower:]' '[:upper:]')
echo -e "${GREEN}✓ 已选择场景 $DEPLOYMENT_MODE${NC}"
echo ""

# 询问访问域名/IP（仅当未通过 --domain 参数指定时）
if [ -z "$SERVER_DOMAIN" ]; then
    echo -e "${BLUE}请输入该平台的访问地址（域名或公网IP）:${NC}"
    echo -e "${YELLOW}提示: 如果仅本地测试可直接回车使用 localhost${NC}"
    read -p "访问地址 [localhost]: " SERVER_DOMAIN
fi
SERVER_DOMAIN=${SERVER_DOMAIN:-localhost}
echo -e "${GREEN}✓ 访问地址已设置为: $SERVER_DOMAIN${NC}"
echo ""

# 1. 检查依赖
echo -e "${BLUE}[1/5] 检查系统环境...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: Python3 未安装${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python3 已安装${NC}"

# 2. 部署 Backend
echo -e "${BLUE}[2/5] 部署 Backend...${NC}"
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
    echo -e "${BLUE}[3/5] 部署 Gateway...${NC}"
    if [ -f "$GATEWAY_DIR/scripts/deploy.sh" ]; then
        cd "$GATEWAY_DIR"
        bash scripts/deploy.sh
        echo -e "${GREEN}✓ Gateway 部署完成${NC}"
    else
        echo -e "${RED}错误: Gateway 部署脚本不存在${NC}"
        exit 1
    fi
else
    echo -e "${BLUE}[3/5] 跳过 Gateway 部署（场景 B 不需要）${NC}"
fi

# 4. 部署 Web 前端
echo -e "${BLUE}[4/5] 部署 Web 前端...${NC}"
if [ -f "$WEB_DIR/scripts/deploy.sh" ]; then
    cd "$WEB_DIR"
    bash scripts/deploy.sh
    echo -e "${GREEN}✓ Web 前端部署完成${NC}"
else
    echo -e "${RED}错误: Web 前端部署脚本不存在${NC}"
fi

# 5. 配置部署模式与参数对账
echo -e "${BLUE}[5/5] 配置系统参数与自动对账...${NC}"

# 配置 Backend
if [ -f "/opt/fota-backend/.env" ]; then
    sed -i "s/^DEPLOYMENT_MODE=.*/DEPLOYMENT_MODE=$DEPLOYMENT_MODE/" /opt/fota-backend/.env
    echo -e "${GREEN}✓ Backend 部署模式已设置为 $DEPLOYMENT_MODE${NC}"

    # 仅场景 A 需要自动同步内部鉴权密钥 (Shared Secret)
    if [ "$DEPLOYMENT_MODE" = "A" ] && [ -f "/opt/litellm-proxy/.env" ]; then
        echo -e "${BLUE}检测到网关模式，正在自动同步内部鉴权密钥...${NC}"
        CURRENT_KEY=$(grep "^LITELLM_MASTER_KEY=" /opt/litellm-proxy/.env | cut -d'=' -f2)
        if [[ "$CURRENT_KEY" == *"xxxx"* ]] || [ -z "$CURRENT_KEY" ]; then
            NEW_KEY="sk-fota-$(openssl rand -hex 16)"
            sed -i "s/^LITELLM_MASTER_KEY=.*/LITELLM_MASTER_KEY=$NEW_KEY/" /opt/litellm-proxy/.env
            sed -i "s/^LITELLM_API_KEY=.*/LITELLM_API_KEY=$NEW_KEY/" /opt/fota-backend/.env
            echo -e "${GREEN}✓ 已自动生成并同步高强度内部鉴权密钥${NC}"
        fi
    fi

    # 检测 Backend POSTGRES_PASSWORD 是否仍为弱默认值（正常情况 backend/deploy.sh 已自动替换）
    PG_PASS=$(grep "^POSTGRES_PASSWORD=" /opt/fota-backend/.env | cut -d'=' -f2)
    if [ "$PG_PASS" = "fota_password" ] || [ -z "$PG_PASS" ]; then
        echo -e "${RED}✗ 安全警告: POSTGRES_PASSWORD 仍为默认弱密码，请立即修改并重新初始化数据库:${NC}"
        echo -e "${YELLOW}  sudo nano /opt/fota-backend/.env${NC}"
    else
        echo -e "${GREEN}✓ POSTGRES_PASSWORD 已设置为强随机密码${NC}"
    fi
fi

# 检测 Gateway LLM API Key 占位值（仅场景 A）
if [ "$DEPLOYMENT_MODE" = "A" ] && [ -f "/opt/litellm-proxy/.env" ]; then
    PLACEHOLDER_KEYS=()
    for var in ANTHROPIC_API_KEY ANTHROPIC_API_KEY_1 ANTHROPIC_API_KEY_2 OPENAI_API_KEY; do
        val=$(grep "^${var}=" /opt/litellm-proxy/.env | cut -d'=' -f2)
        if [[ "$val" == *"xxxx"* ]] || [ -z "$val" ]; then
            PLACEHOLDER_KEYS+=("$var")
        fi
    done
    if [ ${#PLACEHOLDER_KEYS[@]} -gt 0 ]; then
        echo -e "${RED}✗ 以下 LLM API Key 仍为占位值，Gateway 将无法正常工作:${NC}"
        for k in "${PLACEHOLDER_KEYS[@]}"; do
            echo -e "${RED}  - $k${NC}"
        done
        echo -e "${YELLOW}  请立即填写: sudo nano /opt/litellm-proxy/.env${NC}"
    fi
fi

# 检测 Backend LLM API Key 占位值（仅场景 B）
if [ "$DEPLOYMENT_MODE" = "B" ] && [ -f "/opt/fota-backend/.env" ]; then
    ANT_KEY=$(grep "^ANTHROPIC_API_KEY=" /opt/fota-backend/.env | cut -d'=' -f2)
    OAI_KEY=$(grep "^OPENAI_API_KEY=" /opt/fota-backend/.env | cut -d'=' -f2)
    if [ -z "$ANT_KEY" ] && [ -z "$OAI_KEY" ]; then
        echo -e "${RED}✗ ANTHROPIC_API_KEY 和 OPENAI_API_KEY 均为空，Backend 将无法调用 LLM。${NC}"
        echo -e "${YELLOW}  请填写: sudo nano /opt/fota-backend/.env${NC}"
    fi
fi

# 配置 Web (闭环解决浏览器侧的 localhost:8000 陷阱)
if [ -f "/opt/fota-web/.env.local" ]; then
    # (1) Server-side: 指向 127.0.0.1 (Next.js 服务端代理用)
    sed -i "s|^BACKEND_URL=.*|BACKEND_URL=http://127.0.0.1:8000|" /opt/fota-web/.env.local
    
    # (2) Client-side: 指向外部真实域名 (防止浏览器访问 localhost)
    if [ "$SERVER_DOMAIN" = "localhost" ]; then
        sed -i "s|^NEXT_PUBLIC_BACKEND_URL=.*|NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:8000|" /opt/fota-web/.env.local
    else
        # 配合 Nginx 模板中的 /backend-api 路由实现单入口访问
        sed -i "s|^NEXT_PUBLIC_BACKEND_URL=.*|NEXT_PUBLIC_BACKEND_URL=http://$SERVER_DOMAIN/backend-api|" /opt/fota-web/.env.local
    fi
    echo -e "${GREEN}✓ Web 环境变量已完成内外网地址对账闭环${NC}"
fi

# 6. (可选) 配置 Nginx 反向代理 - 适配 conf.d 和 sites-enabled
if command -v nginx &> /dev/null; then
    echo -e "${BLUE}[附加步] 检测到 Nginx，正在尝试配置最优反向代理通路...${NC}"
    NGINX_TEMPLATE="$PROJECT_DIR/scripts/nginx/velab.conf.template"
    
    # 路径探测：优先使用 conf.d (现代标准)，回退使用 sites-available (Debian/Ubuntu 传统)
    if [ -d "/etc/nginx/conf.d" ]; then
        NGINX_CONF_DEST="/etc/nginx/conf.d/velab.conf"
    elif [ -d "/etc/nginx/sites-available" ]; then
        NGINX_CONF_DEST="/etc/nginx/sites-available/velab.conf"
        NGINX_ENABLED_LINK="/etc/nginx/sites-enabled/velab.conf"
    fi

    if [ -n "$NGINX_CONF_DEST" ] && [ -f "$NGINX_TEMPLATE" ]; then
        cp "$NGINX_TEMPLATE" "$NGINX_CONF_DEST"
        sed -i "s/DOMAIN_OR_IP/$SERVER_DOMAIN/g" "$NGINX_CONF_DEST"
        
        # 处理 sites-enabled 软链接
        if [ -n "$NGINX_ENABLED_LINK" ]; then
            ln -sf "$NGINX_CONF_DEST" "$NGINX_ENABLED_LINK"
        fi

        if nginx -t > /dev/null 2>&1; then
            systemctl reload nginx
            echo -e "${GREEN}✓ Nginx 统一入口配置成功: http://$SERVER_DOMAIN${NC}"
        else
            echo -e "${RED}⚠ Nginx 配置文件语法错误，已保留在 $NGINX_CONF_DEST 请手动检查${NC}"
        fi
    fi
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}部署完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

if [ "$DEPLOYMENT_MODE" = "A" ]; then
    echo -e "${BLUE}场景 A 部署完成，访问地址: ${YELLOW}http://$SERVER_DOMAIN${NC}"
    echo ""
    echo -e "${YELLOW}1. 配置网关秘钥 (必做):${NC}"
    echo -e "   sudo nano /opt/litellm-proxy/.env"
    echo -e "   ${YELLOW}填入真实的 ANTHROPIC_API_KEY 等${NC}"
    echo ""
    echo -e "${YELLOW}2. 检查各服务状态:${NC}"
    echo -e "   sudo systemctl status litellm fota-backend fota-web"
else
    echo -e "${BLUE}场景 B 部署完成，访问地址: ${YELLOW}http://$SERVER_DOMAIN${NC}"
    echo ""
    echo -e "${YELLOW}1. 配置 Backend 秘钥:${NC}"
    echo -e "   sudo nano /opt/fota-backend/.env"
    echo -e "   ${YELLOW}填入真实的 ANTHROPIC_API_KEY 和 OPENAI_API_KEY${NC}"
    echo ""
    echo -e "${YELLOW}2. 检查各服务状态:${NC}"
    echo -e "   sudo systemctl status fota-backend fota-web"
fi

echo ""
echo -e "${YELLOW}注意: 如需配置 Nginx 反向代理，请参考各组件的 nginx 目录${NC}"
echo ""
