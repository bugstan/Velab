#!/usr/bin/env bash
# 本机开发环境：清空 Arq/Redis 任务键 + PostgreSQL 业务表数据。
# 危险操作：会删除 fota_db 中下列表内全部行，并清空当前 Redis 数据库中所有键。
# 重要：执行前先停止 FastAPI（main.py）和 Arq Worker，否则 TRUNCATE 会等表锁，可能“卡住”数分钟。
# 兼容：macOS (Homebrew: redis-cli / psql) 与 Linux；可用 VELAB_PSQL、VELAB_REDIS_CLI 指定路径
# 用法（在 backend 目录）:
#   ./scripts/reset_local_state.sh
#   POSTGRES_PASSWORD=xxx REDIS_PASSWORD=xxx ./scripts/reset_local_state.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"
velab_path_prepend_brew
# 可加载同目录下 .env（若存在）
if [[ -f "${BACKEND_DIR}/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${BACKEND_DIR}/.env"
  set +a
fi

PG_USER="${POSTGRES_USER:-postgres}"
PG_PASS="${POSTGRES_PASSWORD:-fota_password}"
PG_HOST="${POSTGRES_HOST:-localhost}"
PG_PORT="${POSTGRES_PORT:-5432}"
PG_DB="${POSTGRES_DB:-fota_db}"

REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
if ! velab_build_redis_cli_array; then
  echo "错误: 未找到 redis-cli。macOS: brew install redis" >&2
  exit 1
fi
PSQL_BIN="$(velab_find_psql 2>/dev/null)" || {
  echo "错误: 未找到 psql。macOS: brew install postgresql@16" >&2
  exit 1
}

echo "==> PostgreSQL: 截断业务表"
export PGPASSWORD="$PG_PASS"
"$PSQL_BIN" -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1 <<'SQL'
-- 子表先列齐，与 cases 一次性 TRUNCATE，避免外键与百万行 DELETE 缓慢
TRUNCATE TABLE
  diagnosis_events,
  raw_log_files,
  confirmed_diagnosis,
  cases
  RESTART IDENTITY CASCADE;
SQL

echo "==> PostgreSQL: 截断缓存/向量/标准事件表（表不存在时忽略）"
set +e
"$PSQL_BIN" -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=0 -c \
  "TRUNCATE TABLE semantic_cache, knowledge_vectors, standard_events RESTART IDENTITY CASCADE" \
  2>/dev/null
set -e

echo "==> PostgreSQL: 确保 pg_trgm 扩展与 GIN 索引存在（已有则忽略）"
export PGPASSWORD="$PG_PASS"
"$PSQL_BIN" -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
    -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" 2>&1 || true
# CONCURRENTLY 不能在事务块内，用独立的 psql 调用
"$PSQL_BIN" -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
    -c "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_diagnosis_events_message_gin_trgm
        ON diagnosis_events USING gin (message gin_trgm_ops);" 2>&1 || true

echo "==> Redis: 清空当前 DB（含 arq:queue、arq:job:*、task_progress:* 等）"
"${VELAB_REDIS_CLI_ARR[@]}" FLUSHDB

echo "==> 完成。请重启: API（main.py/uvicorn）与 Arq Worker（run_worker.py）后再上传。"
echo "    若需同时删本机已上传文件: 删除 \$STORAGE_ROOT 下 uploads/、logs/（见 config 里路径）。"
