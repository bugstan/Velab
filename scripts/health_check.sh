#!/bin/bash
# ============================================================================
# Velab FOTA 诊断系统 - 全栈健康检查脚本
# ============================================================================
# 用途：检查所有服务状态并生成健康检查报告
# 使用：./health_check.sh [--verbose] [--json]
# 退出码：0=所有服务正常，1=部分服务异常，2=关键服务异常
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
JSON_OUTPUT=false
EXIT_CODE=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 服务状态
declare -A SERVICE_STATUS
declare -A SERVICE_MESSAGE

# ============================================================================
# 辅助函数
# ============================================================================

print_header() {
    if [ "$JSON_OUTPUT" = false ]; then
        echo -e "${BLUE}========================================${NC}"
        echo -e "${BLUE}$1${NC}"
        echo -e "${BLUE}========================================${NC}"
    fi
}

print_success() {
    if [ "$JSON_OUTPUT" = false ]; then
        echo -e "${GREEN}✓${NC} $1"
    fi
}

print_warning() {
    if [ "$JSON_OUTPUT" = false ]; then
        echo -e "${YELLOW}⚠${NC} $1"
    fi
    [ $EXIT_CODE -lt 1 ] && EXIT_CODE=1
}

print_error() {
    if [ "$JSON_OUTPUT" = false ]; then
        echo -e "${RED}✗${NC} $1" >&2
    fi
    EXIT_CODE=2
}

print_info() {
    if [ "$VERBOSE" = true ] && [ "$JSON_OUTPUT" = false ]; then
        echo -e "  ${BLUE}ℹ${NC} $1"
    fi
}

# ============================================================================
# 参数解析
# ============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --json|-j)
            JSON_OUTPUT=true
            shift
            ;;
        --help|-h)
            echo "用法: $0 [选项]"
            echo ""
            echo "选项:"
            echo "  --verbose, -v    显示详细信息"
            echo "  --json, -j       以 JSON 格式输出"
            echo "  --help, -h       显示此帮助信息"
            echo ""
            echo "退出码:"
            echo "  0  所有服务正常"
            echo "  1  部分服务异常（非关键）"
            echo "  2  关键服务异常"
            exit 0
            ;;
        *)
            print_error "未知参数: $1"
            exit 2
            ;;
    esac
done

# ============================================================================
# 加载环境变量
# ============================================================================

load_env() {
    if [ -f "$PROJECT_DIR/backend/.env" ]; then
        print_info "加载 backend/.env"
        set -a
        source "$PROJECT_DIR/backend/.env"
        set +a
    fi
    
    if [ -f "$PROJECT_DIR/gateway/.env" ]; then
        print_info "加载 gateway/.env"
        set -a
        source "$PROJECT_DIR/gateway/.env"
        set +a
    fi
}

# ============================================================================
# 1. 检查 Backend 服务
# ============================================================================

check_backend() {
    print_header "检查 Backend 服务"
    
    local backend_url="${BACKEND_URL:-http://localhost:8000}"
    print_info "Backend URL: $backend_url"
    
    # 检查健康端点
    if curl -s -f -m 5 "$backend_url/health" > /dev/null 2>&1; then
        SERVICE_STATUS[backend]="healthy"
        SERVICE_MESSAGE[backend]="Backend 服务运行正常"
        print_success "Backend 服务运行正常"
        
        # 获取版本信息
        if [ "$VERBOSE" = true ]; then
            local version=$(curl -s -m 5 "$backend_url/health" | python3 -c "import sys, json; print(json.load(sys.stdin).get('version', 'unknown'))" 2>/dev/null || echo "unknown")
            print_info "版本: $version"
        fi
    else
        SERVICE_STATUS[backend]="unhealthy"
        SERVICE_MESSAGE[backend]="Backend 服务无响应"
        print_error "Backend 服务无响应"
    fi
}

# ============================================================================
# 2. 检查 Gateway 服务
# ============================================================================

check_gateway() {
    print_header "检查 Gateway 服务（可选）"
    
    local gateway_url="${LITELLM_GATEWAY_URL:-http://localhost:4000}"
    print_info "Gateway URL: $gateway_url"
    
    # 检查健康端点
    if curl -s -f -m 5 "$gateway_url/health" > /dev/null 2>&1; then
        SERVICE_STATUS[gateway]="healthy"
        SERVICE_MESSAGE[gateway]="Gateway 服务运行正常"
        print_success "Gateway 服务运行正常"
    else
        SERVICE_STATUS[gateway]="unhealthy"
        SERVICE_MESSAGE[gateway]="Gateway 服务无响应（可选服务）"
        print_warning "Gateway 服务无响应（可选服务）"
    fi
}

# ============================================================================
# 3. 检查 Web 服务
# ============================================================================

check_web() {
    print_header "检查 Web 服务"
    
    local web_url="${WEB_URL:-http://localhost:3000}"
    print_info "Web URL: $web_url"
    
    # 检查首页
    if curl -s -f -m 5 "$web_url" > /dev/null 2>&1; then
        SERVICE_STATUS[web]="healthy"
        SERVICE_MESSAGE[web]="Web 服务运行正常"
        print_success "Web 服务运行正常"
    else
        SERVICE_STATUS[web]="unhealthy"
        SERVICE_MESSAGE[web]="Web 服务无响应"
        print_error "Web 服务无响应"
    fi
}

# ============================================================================
# 4. 检查 PostgreSQL
# ============================================================================

check_postgresql() {
    print_header "检查 PostgreSQL"
    
    if [ -z "$DATABASE_URL" ]; then
        SERVICE_STATUS[postgresql]="unknown"
        SERVICE_MESSAGE[postgresql]="DATABASE_URL 未设置"
        print_warning "DATABASE_URL 未设置，跳过检查"
        return
    fi
    
    print_info "测试数据库连接..."
    
    python3 << 'EOF'
import sys
import os
try:
    import psycopg2
    from urllib.parse import urlparse
    
    db_url = os.environ.get('DATABASE_URL', '')
    result = urlparse(db_url)
    
    conn = psycopg2.connect(
        database=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port or 5432,
        connect_timeout=5
    )
    
    cursor = conn.cursor()
    cursor.execute('SELECT 1')
    cursor.close()
    conn.close()
    
    print("healthy")
    sys.exit(0)
    
except ImportError:
    print("error:psycopg2 not installed")
    sys.exit(1)
except Exception as e:
    print(f"error:{e}")
    sys.exit(1)
EOF
    
    local result=$?
    local output=$(python3 << 'EOF'
import sys
import os
try:
    import psycopg2
    from urllib.parse import urlparse
    
    db_url = os.environ.get('DATABASE_URL', '')
    result = urlparse(db_url)
    
    conn = psycopg2.connect(
        database=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port or 5432,
        connect_timeout=5
    )
    
    cursor = conn.cursor()
    cursor.execute('SELECT 1')
    cursor.close()
    conn.close()
    
    print("healthy")
    
except ImportError:
    print("error:psycopg2 not installed")
except Exception as e:
    print(f"error:{e}")
EOF
)
    
    if [ $result -eq 0 ]; then
        SERVICE_STATUS[postgresql]="healthy"
        SERVICE_MESSAGE[postgresql]="PostgreSQL 连接正常"
        print_success "PostgreSQL 连接正常"
    else
        SERVICE_STATUS[postgresql]="unhealthy"
        SERVICE_MESSAGE[postgresql]="PostgreSQL 连接失败"
        print_error "PostgreSQL 连接失败"
    fi
}

# ============================================================================
# 5. 检查 Redis
# ============================================================================

check_redis() {
    print_header "检查 Redis（可选）"
    
    if [ -z "$REDIS_URL" ]; then
        SERVICE_STATUS[redis]="unknown"
        SERVICE_MESSAGE[redis]="REDIS_URL 未设置"
        print_info "REDIS_URL 未设置，跳过检查"
        return
    fi
    
    print_info "测试 Redis 连接..."
    
    python3 << 'EOF'
import sys
import os
try:
    import redis
    
    redis_url = os.environ.get('REDIS_URL', '')
    r = redis.from_url(redis_url, socket_connect_timeout=5)
    r.ping()
    
    print("healthy")
    sys.exit(0)
    
except ImportError:
    print("error:redis not installed")
    sys.exit(1)
except Exception as e:
    print(f"error:{e}")
    sys.exit(1)
EOF
    
    if [ $? -eq 0 ]; then
        SERVICE_STATUS[redis]="healthy"
        SERVICE_MESSAGE[redis]="Redis 连接正常"
        print_success "Redis 连接正常"
    else
        SERVICE_STATUS[redis]="unhealthy"
        SERVICE_MESSAGE[redis]="Redis 连接失败（可选服务）"
        print_warning "Redis 连接失败（可选服务）"
    fi
}

# ============================================================================
# 6. 检查 MinIO
# ============================================================================

check_minio() {
    print_header "检查 MinIO（可选）"
    
    if [ -z "$MINIO_ENDPOINT" ] || [ -z "$MINIO_ACCESS_KEY" ] || [ -z "$MINIO_SECRET_KEY" ]; then
        SERVICE_STATUS[minio]="unknown"
        SERVICE_MESSAGE[minio]="MinIO 配置未完整设置"
        print_info "MinIO 配置未完整设置，跳过检查"
        return
    fi
    
    print_info "测试 MinIO 连接..."
    
    python3 << 'EOF'
import sys
import os
try:
    from minio import Minio
    
    endpoint = os.environ.get('MINIO_ENDPOINT', '').replace('http://', '').replace('https://', '')
    access_key = os.environ.get('MINIO_ACCESS_KEY', '')
    secret_key = os.environ.get('MINIO_SECRET_KEY', '')
    
    client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)
    client.list_buckets()
    
    print("healthy")
    sys.exit(0)
    
except ImportError:
    print("error:minio not installed")
    sys.exit(1)
except Exception as e:
    print(f"error:{e}")
    sys.exit(1)
EOF
    
    if [ $? -eq 0 ]; then
        SERVICE_STATUS[minio]="healthy"
        SERVICE_MESSAGE[minio]="MinIO 连接正常"
        print_success "MinIO 连接正常"
    else
        SERVICE_STATUS[minio]="unhealthy"
        SERVICE_MESSAGE[minio]="MinIO 连接失败（可选服务）"
        print_warning "MinIO 连接失败（可选服务）"
    fi
}

# ============================================================================
# 7. 生成报告
# ============================================================================

generate_report() {
    if [ "$JSON_OUTPUT" = true ]; then
        # JSON 格式输出
        echo "{"
        echo "  \"timestamp\": \"$(date -u +"%Y-%m-%dT%H:%M:%SZ")\","
        echo "  \"overall_status\": \"$([ $EXIT_CODE -eq 0 ] && echo "healthy" || echo "unhealthy")\","
        echo "  \"services\": {"
        
        local first=true
        for service in "${!SERVICE_STATUS[@]}"; do
            if [ "$first" = false ]; then
                echo ","
            fi
            first=false
            echo -n "    \"$service\": {"
            echo -n "\"status\": \"${SERVICE_STATUS[$service]}\", "
            echo -n "\"message\": \"${SERVICE_MESSAGE[$service]}\""
            echo -n "}"
        done
        
        echo ""
        echo "  }"
        echo "}"
    else
        # 文本格式输出
        print_header "健康检查总结"
        
        echo "服务状态:"
        for service in backend web postgresql gateway redis minio; do
            if [ -n "${SERVICE_STATUS[$service]}" ]; then
                local status="${SERVICE_STATUS[$service]}"
                local message="${SERVICE_MESSAGE[$service]}"
                
                case $status in
                    healthy)
                        echo -e "  ${GREEN}✓${NC} $service: $message"
                        ;;
                    unhealthy)
                        echo -e "  ${RED}✗${NC} $service: $message"
                        ;;
                    unknown)
                        echo -e "  ${YELLOW}?${NC} $service: $message"
                        ;;
                esac
            fi
        done
        
        echo ""
        case $EXIT_CODE in
            0)
                echo -e "${GREEN}✓ 所有服务运行正常${NC}"
                ;;
            1)
                echo -e "${YELLOW}⚠ 部分可选服务异常，核心功能可用${NC}"
                ;;
            2)
                echo -e "${RED}✗ 关键服务异常，请检查配置${NC}"
                ;;
        esac
    fi
}

# ============================================================================
# 主函数
# ============================================================================

main() {
    if [ "$JSON_OUTPUT" = false ]; then
        echo -e "${BLUE}Velab 全栈健康检查${NC}"
        echo -e "${BLUE}时间: $(date)${NC}"
        echo ""
    fi
    
    load_env
    
    check_backend
    check_web
    check_postgresql
    check_gateway
    check_redis
    check_minio
    
    generate_report
    
    exit $EXIT_CODE
}

main
