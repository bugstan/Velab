#!/usr/bin/env bash
# =============================================================================
# Velab / FOTA 脚本：跨平台公共函数（macOS 与 Linux/Ubuntu）
# =============================================================================
# 用法：在其它脚本中（在确定 BACKEND_DIR 或当前为 backend 目录后）:
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   # shellcheck source=scripts/lib/common.sh
#   source "$SCRIPT_DIR/lib/common.sh"   # 若从 backend 调 scripts/foo.sh，用 dirname 两次
# 或: source "$(dirname "$0")/lib/common.sh"  # 当脚本在 scripts/ 下时
#
# 环境变量可覆盖:
#   VELAB_VENV_DIR   显式指定虚拟环境绝对路径
#   VELAB_REDIS_CLI  显式指定 redis-cli 可执行文件
#   VELAB_PSQL       显式指定 psql 可执行文件
# =============================================================================

# 可重复 source，避免覆盖用户已设值
: "${VELAB_UNAME_S:=$(uname -s 2>/dev/null || echo unknown)}"
case "$VELAB_UNAME_S" in
  Darwin) VELAB_OS=macos ;;
  Linux)  VELAB_OS=linux ;;
  *)      VELAB_OS=other ;;
esac

# -----------------------------------------------------------------------------
# 虚拟环境：优先 VELAB_VENV_DIR；否则有 .venv / venv 则用已有；
# 都不存在时：mac 默认 .venv，Linux 默认 venv
# -----------------------------------------------------------------------------
velab_resolve_venv_dir() {
  local root="${1:-.}"
  if [ -n "${VELAB_VENV_DIR:-}" ]; then
    printf '%s' "$VELAB_VENV_DIR"
    return
  fi
  if [ -d "$root/.venv" ] && [ -x "$root/.venv/bin/activate" ]; then
    printf '%s' "$root/.venv"
  elif [ -d "$root/venv" ] && [ -x "$root/venv/bin/activate" ]; then
    printf '%s' "$root/venv"
  elif [ "$VELAB_OS" = "macos" ]; then
    printf '%s' "$root/.venv"
  else
    printf '%s' "$root/venv"
  fi
}

# 在 BACKEND_DIR 上设置 VELAB_VENV_DIR 与 VELAB_PYTHON
velab_bootstrap_venv() {
  local root="${1:?backend root required}"
  export VELAB_VENV_DIR
  VELAB_VENV_DIR="$(velab_resolve_venv_dir "$root")"
  if [ -x "$VELAB_VENV_DIR/bin/python" ]; then
    export VELAB_PYTHON="$VELAB_VENV_DIR/bin/python"
  else
    export VELAB_PYTHON="python3"
  fi
}

# -----------------------------------------------------------------------------
# 在 PATH 中解析命令，macOS 上常见 Homebrew 路径
# -----------------------------------------------------------------------------
velab_path_prepend_brew() {
  if [ "$VELAB_OS" != "macos" ]; then
    return 0
  fi
  local p
  for p in /opt/homebrew/bin /opt/homebrew/sbin /usr/local/bin /usr/local/sbin; do
    if [ -d "$p" ]; then
      case ":$PATH:" in
        *":$p:"*) ;;
        *) export PATH="$p:$PATH" ;;
      esac
    fi
  done
}

# redis-cli: 可设置 VELAB_REDIS_CLI
velab_find_redis_cli() {
  if [ -n "${VELAB_REDIS_CLI:-}" ] && [ -x "${VELAB_REDIS_CLI}" ]; then
    printf '%s' "$VELAB_REDIS_CLI"
    return
  fi
  if command -v redis-cli &>/dev/null; then
    command -v redis-cli
    return
  fi
  local c
  for c in /opt/homebrew/bin/redis-cli /opt/homebrew/opt/redis/bin/redis-cli \
           /usr/local/bin/redis-cli /usr/local/opt/redis/bin/redis-cli; do
    if [ -x "$c" ]; then
      printf '%s' "$c"
      return
    fi
  done
  return 1
}

# psql: 可设置 VELAB_PSQL
velab_find_psql() {
  if [ -n "${VELAB_PSQL:-}" ] && [ -x "${VELAB_PSQL}" ]; then
    printf '%s' "$VELAB_PSQL"
    return
  fi
  if command -v psql &>/dev/null; then
    command -v psql
    return
  fi
  local c v
  for v in 16 15 14 13; do
    for c in \
      "/opt/homebrew/opt/postgresql@$v/bin/psql" \
      "/usr/local/opt/postgresql@$v/bin/psql" \
      "/opt/homebrew/Cellar/postgresql@$v"/*/bin/psql; do
      if [ -x "$c" ] 2>/dev/null; then
        printf '%s' "$c"
        return
      fi
    done
  done
  return 1
}

# 确保能调用 redis-cli 数组（与 reset 脚本一致）
velab_build_redis_cli_array() {
  # shellcheck disable=SC2207
  local rc
  if ! rc="$(velab_find_redis_cli 2>/dev/null)"; then
    return 1
  fi
  VELAB_REDIS_CLI_ARR=("$rc" -h "${REDIS_HOST:-127.0.0.1}" -p "${REDIS_PORT:-6379}")
  if [ -n "${REDIS_PASSWORD:-}" ]; then
    VELAB_REDIS_CLI_ARR+=(-a "$REDIS_PASSWORD" --no-auth-warning)
  fi
  return 0
}

# -----------------------------------------------------------------------------
# 以管理员身份执行 psql 读标准输入（Linux: postgres 系统用户；macOS: 本机连 postgres 库，常用 Homebrew 超户）
# 用法: velab_run_psql_admin <<'EOSQL' ... EOSQL
# -----------------------------------------------------------------------------
velab_run_psql_admin() {
  if [ "$VELAB_OS" = "macos" ]; then
    local psql
    if ! psql="$(velab_find_psql 2>/dev/null)"; then
      echo "velab: 未找到 psql。macOS: brew install postgresql@16" >&2
      return 1
    fi
    # Homebrew 通常以当前用户为超户，连接本机默认 socket 的 postgres 库
    "$psql" -v ON_ERROR_STOP=1 -d postgres
  else
    if ! command -v sudo &>/dev/null; then
      echo "velab: 需要 sudo 以 postgres 用户执行 psql" >&2
      return 1
    fi
    sudo -u postgres psql -v ON_ERROR_STOP=1 --username postgres
  fi
}

velab_print_os_hint() {
  echo "当前平台: $VELAB_OS ($VELAB_UNAME_S)  虚拟环境目录: ${VELAB_VENV_DIR:-未设置}"
}
