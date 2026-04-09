#!/bin/bash
# ============================================================
# FOTA 智能诊断平台 - 基础设施级别 PostgreSQL 初始化脚本
# ============================================================
# 用途：配置基础数据库实例（建库、建用户）
# 注意：这仅做基础设施搭建。业务表的生成在 deploy.sh 内自动完成。
# 推荐执行环境：本机 PostgreSQL
# 使用：chmod +x ./init_postgres.sh && ./init_postgres.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}FOTA PostgreSQL 基础设施初始化脚本${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 1. 检查是否存在 psql 命令
if ! command -v psql &> /dev/null; then
    echo -e "${RED}错误: 未检测到 PostgreSQL (psql 命令未找到)${NC}"
    echo -e "${YELLOW}如未安装，请考虑在 Ubuntu / Debian 执行:${NC}"
    echo -e "sudo apt update && sudo apt install postgresql postgresql-contrib"
    exit 1
fi

echo -e "${BLUE}环境检测通过，开始初始化 PostgreSQL 用户与数据库...${NC}"

# 从 .env 中加载变量（如果文件存在）
ENV_FILE="$(dirname "$0")/../.env"
DB_USER="postgres"
DB_PASS="fota_password"
DB_NAME="fota_db"

if [ -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}检测到 .env 文件，尝试使用其中的配置...${NC}"
    # 读取环境变量，容错处理
    source "$ENV_FILE"
    DB_USER=${POSTGRES_USER:-$DB_USER}
    DB_PASS=${POSTGRES_PASSWORD:-$DB_PASS}
    DB_NAME=${POSTGRES_DB:-$DB_NAME}
fi

echo -e "  - 目标数据库名: ${DB_NAME}"
echo -e "  - 管理员账户名: ${DB_USER}"
echo -e "  - 账户访问密码: (已隐藏)"
echo ""

# 为了防止当前非 postgres 实体用户执行，使用 sudo -u postgres 拉起 psql 执行
# 注意：这要求机器上 PostgreSQL 服务处在正常运行状态（systemctl start postgresql）
sudo -u postgres psql -v ON_ERROR_STOP=1 --username postgres <<-EOSQL
    -- (1) 如果是默认的 postgres 用户，确保给他设立密码；或者创建一个新用户
    DO \$\$
    BEGIN
      IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${DB_USER}') THEN
        CREATE ROLE ${DB_USER} WITH LOGIN PASSWORD '${DB_PASS}';
      ELSE
        ALTER ROLE ${DB_USER} WITH PASSWORD '${DB_PASS}';
      END IF;
    END
    \$\$;
    
    -- (2) 检查数据库是否存在，不存在则创建
    SELECT 'CREATE DATABASE ${DB_NAME} OWNER ${DB_USER}'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')\\gexec
EOSQL

echo -e "${GREEN}✓ 数据库及用户基础设施准备完毕！${NC}"
echo -e "${YELLOW}提示: 如果还需要 pgvector 等高阶扩展库，请根据需要连接数据库执行 'CREATE EXTENSION vector;'${NC}"
