#!/bin/bash
# 本地开发启动：同时启动 Backend + Frontend，按条件启动 LiteLLM Gateway
# 用法：./scripts/dev.sh
# 退出：Ctrl+C

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
WEB_DIR="$ROOT_DIR/web"
GATEWAY_DIR="$ROOT_DIR/gateway"

# 解析虚拟环境路径
if [ -d "$BACKEND_DIR/.venv" ]; then
  VENV_DIR="$BACKEND_DIR/.venv"
else
  VENV_DIR="$BACKEND_DIR/venv"
fi

# 停止占用指定端口的旧进程（先 SIGTERM，1s 后强制 SIGKILL）
stop_port() {
  local port=$1
  local pids
  pids=$(lsof -ti:"$port" 2>/dev/null)
  if [ -n "$pids" ]; then
    echo "==> 停止端口 $port 上的旧进程 (PID: $pids)"
    echo "$pids" | xargs kill -TERM 2>/dev/null
    sleep 1
    pids=$(lsof -ti:"$port" 2>/dev/null)
    [ -n "$pids" ] && echo "$pids" | xargs kill -9 2>/dev/null
  fi
}

# Ctrl+C 同时停止所有子进程
PIDS=()
cleanup() {
  echo ""
  echo "停止所有服务..."
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null; done
  wait 2>/dev/null
  exit 0
}
trap cleanup INT TERM

# 停止已有旧服务
stop_port 8000
stop_port 3000

echo "==> 启动 Backend  (http://localhost:8000)"
(cd "$BACKEND_DIR" && source "$VENV_DIR/bin/activate" && exec python main.py) &
PIDS+=($!)

echo "==> 启动 Frontend (http://localhost:3000)"
(cd "$WEB_DIR" && exec npm run dev) &
PIDS+=($!)

# ── 智能判断是否启动 Gateway ──
# 场景 B（直连 LLM）不需要 Gateway；场景 A 才需要
DEPLOY_MODE=$(grep -E '^DEPLOYMENT_MODE=' "$BACKEND_DIR/.env" 2>/dev/null | cut -d= -f2 | tr -d '[:space:]"')
if [ "$DEPLOY_MODE" = "B" ]; then
  echo "==> Gateway 跳过（DEPLOYMENT_MODE=B，直连 LLM）"
elif [ ! -f "$GATEWAY_DIR/.env" ]; then
  echo "==> Gateway 跳过（gateway/.env 不存在）"
elif ! command -v litellm &>/dev/null; then
  echo "==> Gateway 跳过（litellm 未安装）"
else
  stop_port 4000
  echo "==> 启动 Gateway  (http://127.0.0.1:4000)"
  (cd "$GATEWAY_DIR" && exec litellm --config config.yaml --host 127.0.0.1 --port 4000) &
  PIDS+=($!)
fi

wait
