#!/bin/bash
# ============================================================================
# Velab FOTA 诊断系统 - Redis 初始化脚本
# ============================================================================
# 用途：初始化 Redis 命名空间、设置默认配置、测试连接
# 使用：./init_redis.sh [--redis-url REDIS_URL] [--verbose]
# 退出码：0=成功，1=失败
# ============================================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 默认配置
VERBOSE=false
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
# shellcheck source=lib/common.sh
# shellcheck disable=SC1090
source "$SCRIPT_DIR/lib/common.sh"
velab_path_prepend_brew
velab_bootstrap_venv "$BACKEND_DIR"
PY="${VELAB_PYTHON:-python3}"

# ============================================================================
# 辅助函数
# ============================================================================

print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1" >&2
}

print_info() {
    if [ "$VERBOSE" = true ]; then
        echo -e "  ${BLUE}ℹ${NC} $1"
    fi
}

# ============================================================================
# 参数解析
# ============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        --redis-url)
            REDIS_URL="$2"
            shift 2
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            echo "用法: $0 [选项]"
            echo ""
            echo "选项:"
            echo "  --redis-url URL    Redis 连接 URL（默认从 .env 读取）"
            echo "  --verbose, -v      显示详细信息"
            echo "  --help, -h         显示此帮助信息"
            echo ""
            echo "示例:"
            echo "  $0"
            echo "  $0 --redis-url redis://localhost:6379/0"
            echo "  $0 --verbose"
            exit 0
            ;;
        *)
            print_error "未知参数: $1"
            exit 1
            ;;
    esac
done

# ============================================================================
# 加载环境变量
# ============================================================================

if [ -z "$REDIS_URL" ]; then
    if [ -f "$BACKEND_DIR/.env" ]; then
        print_info "从 .env 文件加载配置"
        set -a
        source "$BACKEND_DIR/.env"
        set +a
    fi
fi

# 若仍无 REDIS_URL，从分散变量自动拼接（与项目标准 env 变量对齐）
if [ -z "$REDIS_URL" ]; then
    _host="${REDIS_HOST:-localhost}"
    _port="${REDIS_PORT:-6379}"
    _pass="${REDIS_PASSWORD:-}"
    if [ -n "$_pass" ]; then
        REDIS_URL="redis://:${_pass}@${_host}:${_port}/0"
    else
        REDIS_URL="redis://${_host}:${_port}/0"
    fi
    print_info "从 REDIS_HOST/PORT/PASSWORD 拼接 REDIS_URL: $REDIS_URL"
fi
export REDIS_URL

# ============================================================================
# Redis 初始化
# ============================================================================

init_redis() {
    print_header "初始化 Redis"
    
    print_info "Redis URL: $REDIS_URL"
    
    "$PY" << EOF
import sys
import os
import json
from datetime import datetime

try:
    import redis
except ImportError:
    print("错误: 未安装 redis 包")
    print("请运行: pip install redis")
    sys.exit(1)

# 连接 Redis
redis_url = os.environ.get('REDIS_URL', '')
print(f"连接到 Redis: {redis_url}")

try:
    r = redis.from_url(redis_url, decode_responses=True)
    r.ping()
    print("✓ Redis 连接成功")
except Exception as e:
    print(f"✗ Redis 连接失败: {e}")
    sys.exit(1)

# ============================================================================
# 1. 创建命名空间前缀
# ============================================================================
print("\n初始化命名空间...")

NAMESPACES = {
    'session': 'velab:session:',      # 用户会话
    'cache': 'velab:cache:',          # 缓存数据
    'queue': 'velab:queue:',          # 任务队列
    'lock': 'velab:lock:',            # 分布式锁
    'counter': 'velab:counter:',      # 计数器
    'config': 'velab:config:',        # 配置缓存
}

# 存储命名空间配置
r.hset('velab:namespaces', mapping=NAMESPACES)
print(f"✓ 创建 {len(NAMESPACES)} 个命名空间")

# ============================================================================
# 2. 设置默认配置
# ============================================================================
print("\n设置默认配置...")

DEFAULT_CONFIG = {
    'session_ttl': '3600',                    # 会话过期时间（秒）
    'cache_ttl': '1800',                      # 缓存过期时间（秒）
    'max_queue_size': '10000',                # 最大队列长度
    'lock_timeout': '30',                     # 锁超时时间（秒）
    'rate_limit_requests': '100',             # 速率限制（请求数）
    'rate_limit_window': '60',                # 速率限制窗口（秒）
}

for key, value in DEFAULT_CONFIG.items():
    r.hset('velab:config:default', key, value)
    print(f"  ✓ {key} = {value}")

print(f"✓ 设置 {len(DEFAULT_CONFIG)} 个默认配置项")

# ============================================================================
# 3. 初始化计数器
# ============================================================================
print("\n初始化计数器...")

COUNTERS = [
    'total_requests',
    'total_errors',
    'total_sessions',
    'total_cache_hits',
    'total_cache_misses',
]

for counter in COUNTERS:
    r.set(f'velab:counter:{counter}', 0)
    print(f"  ✓ {counter} = 0")

print(f"✓ 初始化 {len(COUNTERS)} 个计数器")

# ============================================================================
# 4. 设置系统信息
# ============================================================================
print("\n设置系统信息...")

system_info = {
    'initialized_at': datetime.utcnow().isoformat(),
    'version': '1.0.0',
    'environment': os.environ.get('ENVIRONMENT', 'development'),
}

r.hset('velab:system:info', mapping=system_info)
print(f"✓ 系统信息已设置")

# ============================================================================
# 5. 测试基本操作
# ============================================================================
print("\n测试基本操作...")

# 测试 SET/GET
test_key = 'velab:test:connection'
test_value = 'test_value_' + datetime.utcnow().isoformat()
r.setex(test_key, 60, test_value)
retrieved = r.get(test_key)

if retrieved == test_value:
    print("✓ SET/GET 操作正常")
    r.delete(test_key)
else:
    print("✗ SET/GET 操作失败")
    sys.exit(1)

# 测试 HASH 操作
test_hash = 'velab:test:hash'
r.hset(test_hash, 'field1', 'value1')
r.hset(test_hash, 'field2', 'value2')
hash_data = r.hgetall(test_hash)

if len(hash_data) == 2:
    print("✓ HASH 操作正常")
    r.delete(test_hash)
else:
    print("✗ HASH 操作失败")
    sys.exit(1)

# 测试 LIST 操作
test_list = 'velab:test:list'
r.rpush(test_list, 'item1', 'item2', 'item3')
list_len = r.llen(test_list)

if list_len == 3:
    print("✓ LIST 操作正常")
    r.delete(test_list)
else:
    print("✗ LIST 操作失败")
    sys.exit(1)

# ============================================================================
# 6. 显示 Redis 信息
# ============================================================================
print("\n" + "="*40)
print("Redis 信息")
print("="*40)

info = r.info()
print(f"Redis 版本: {info['redis_version']}")
print(f"运行模式: {info['redis_mode']}")
print(f"已用内存: {info['used_memory_human']}")
print(f"连接客户端数: {info['connected_clients']}")
print(f"总键数: {r.dbsize()}")

print("\n✓ Redis 初始化完成")
sys.exit(0)
EOF

    if [ $? -eq 0 ]; then
        print_success "Redis 初始化成功"
        return 0
    else
        print_error "Redis 初始化失败"
        return 1
    fi
}

# ============================================================================
# 主函数
# ============================================================================

main() {
    echo -e "${BLUE}Velab Redis 初始化${NC}"
    echo ""
    
    if init_redis; then
        echo ""
        print_success "所有操作完成"
        exit 0
    else
        echo ""
        print_error "初始化失败"
        exit 1
    fi
}

main
