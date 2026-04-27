#!/bin/bash
# ============================================================
# FOTA 智能诊断平台 - 基础设施级别 PostgreSQL 初始化脚本
# ============================================================
# 用途：配置基础数据库实例（建库、建用户）
# 注意：这仅做基础设施搭建。业务表的生成在 deploy.sh 内自动完成。
# 支持：Linux (systemd + postgres 系统用户) / macOS (Homebrew，以当前用户为超户)
# 使用：在 backend 目录: chmod +x ./scripts/init_postgres.sh && ./scripts/init_postgres.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"
velab_path_prepend_brew
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
velab_bootstrap_venv "$BACKEND_DIR"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}FOTA PostgreSQL 基础设施初始化脚本${NC}"
echo -e "${GREEN}========================================${NC}"
velab_print_os_hint
echo ""

# 0. 先尝试启动本机服务（与 psql 是否已在 PATH 无关）
if [ "$VELAB_OS" = "linux" ]; then
  if ! systemctl is-active --quiet postgresql 2>/dev/null && ! service postgresql status &>/dev/null; then
    echo -e "${YELLOW}尝试启动 postgresql 服务 (systemd)...${NC}"
    systemctl start postgresql 2>/dev/null || service postgresql start 2>/dev/null || true
  fi
elif [ "$VELAB_OS" = "macos" ]; then
  echo -e "${YELLOW}macOS: 若未运行，可执行: brew services start postgresql@16${NC}"
  if command -v brew &>/dev/null; then
    for ver in 16 15; do
      if brew list "postgresql@$ver" &>/dev/null; then
        brew services start "postgresql@$ver" 2>/dev/null && break
      fi
    done
  fi
  sleep 1
fi

# 1. 检查 psql
if ! velab_find_psql &>/dev/null; then
    echo -e "${RED}错误: 未检测到 PostgreSQL (psql)${NC}"
    echo -e "${YELLOW}Ubuntu/Debian:${NC} sudo apt install postgresql postgresql-contrib"
    echo -e "${YELLOW}macOS (Homebrew):${NC} brew install postgresql@16 && brew services start postgresql@16"
    exit 1
fi

function initialize_db() {
    echo -e "${BLUE}环境检测通过，开始初始化 PostgreSQL 用户与数据库...${NC}"

# 从 .env 中加载变量（如果文件存在）
ENV_FILE="${SCRIPT_DIR}/../.env"
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

# Linux: sudo -u postgres；macOS: 以当前用户连本机 postgres（常见 Homebrew 超户）
velab_run_psql_admin <<-EOSQL
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
    echo -e "${YELLOW}重要提示：${NC}"
    if [ "$VELAB_OS" = "linux" ]; then
      echo -e "  1. 如连接失败，请检查 /etc/postgresql/<version>/main/pg_hba.conf（md5/scram）。"
      echo -e "  2. 若还需要向量检索: CREATE EXTENSION vector;"
    else
      echo -e "  1. macOS: 数据目录在 brew 前缀下，认证见 \$(brew --prefix postgresql*)/ 说明。"
      echo -e "  2. 若还需要向量检索: 在 fota_db 中执行 CREATE EXTENSION vector;"
    fi
    return 0
}

# ============================================================
# 主逻辑
# ============================================================
initialize_db
