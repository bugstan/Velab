#!/bin/bash
# ============================================================================
# Velab FOTA 诊断系统 - 后端环境检查脚本
# ============================================================================
# 用途：检查 Python 环境、依赖包、环境变量和外部服务连接
# 使用：./check_env.sh [--verbose] [--silent]
# 退出码：0=成功，1=警告，2=错误
# ============================================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 默认配置
VERBOSE=false
SILENT=false
EXIT_CODE=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"

# ============================================================================
# 辅助函数
# ============================================================================

print_header() {
    if [ "$SILENT" = false ]; then
        echo -e "${BLUE}========================================${NC}"
        echo -e "${BLUE}$1${NC}"
        echo -e "${BLUE}========================================${NC}"
    fi
}

print_success() {
    if [ "$SILENT" = false ]; then
        echo -e "${GREEN}✓${NC} $1"
    fi
}

print_warning() {
    if [ "$SILENT" = false ]; then
        echo -e "${YELLOW}⚠${NC} $1"
    fi
    [ $EXIT_CODE -lt 1 ] && EXIT_CODE=1
}

print_error() {
    echo -e "${RED}✗${NC} $1" >&2
    EXIT_CODE=2
}

print_info() {
    if [ "$VERBOSE" = true ] && [ "$SILENT" = false ]; then
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
        --silent|-s)
            SILENT=true
            shift
            ;;
        --help|-h)
            echo "用法: $0 [选项]"
            echo ""
            echo "选项:"
            echo "  --verbose, -v    显示详细信息"
            echo "  --silent, -s     静默模式（仅显示错误）"
            echo "  --help, -h       显示此帮助信息"
            echo ""
            echo "退出码:"
            echo "  0  所有检查通过"
            echo "  1  存在警告"
            echo "  2  存在错误"
            exit 0
            ;;
        *)
            print_error "未知参数: $1"
            exit 2
            ;;
    esac
done

# ============================================================================
# 1. Python 版本检查
# ============================================================================

check_python_version() {
    print_header "检查 Python 版本"
    
    if ! command -v python3 &> /dev/null; then
        print_error "未找到 python3 命令"
        return
    fi
    
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    print_info "检测到 Python 版本: $PYTHON_VERSION"
    
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
    
    if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
        print_error "Python 版本过低（需要 ≥3.10，当前 $PYTHON_VERSION）"
    else
        print_success "Python 版本符合要求: $PYTHON_VERSION"
    fi
}

# ============================================================================
# 2. 依赖包检查
# ============================================================================

check_dependencies() {
    print_header "检查 Python 依赖包"
    
    if [ ! -f "$BACKEND_DIR/requirements.txt" ]; then
        print_error "未找到 requirements.txt 文件"
        return
    fi
    
    print_info "检查 requirements.txt 中的依赖包..."
    
    # 关键依赖包列表
    CRITICAL_PACKAGES=(
        "fastapi"
        "uvicorn"
        "sqlalchemy"
        "psycopg2-binary"
        "pydantic"
        "python-dotenv"
    )
    
    MISSING_PACKAGES=()
    
    for package in "${CRITICAL_PACKAGES[@]}"; do
        if python3 -c "import importlib.util; import sys; sys.exit(0 if importlib.util.find_spec('${package//-/_}') else 1)" 2>/dev/null; then
            print_info "✓ $package"
        else
            MISSING_PACKAGES+=("$package")
            print_warning "缺少依赖包: $package"
        fi
    done
    
    if [ ${#MISSING_PACKAGES[@]} -eq 0 ]; then
        print_success "所有关键依赖包已安装"
    else
        print_warning "缺少 ${#MISSING_PACKAGES[@]} 个依赖包，运行: pip install -r requirements.txt"
    fi
}

# ============================================================================
# 3. 环境变量检查
# ============================================================================

check_env_variables() {
    print_header "检查环境变量"
    
    # 加载 .env 文件
    if [ -f "$BACKEND_DIR/.env" ]; then
        print_info "加载 .env 文件"
        set -a
        source "$BACKEND_DIR/.env"
        set +a
    else
        print_warning "未找到 .env 文件"
    fi
    
    # 必需的环境变量
    REQUIRED_VARS=(
        "DATABASE_URL"
        "SECRET_KEY"
    )
    
    # 可选的环境变量
    OPTIONAL_VARS=(
        "REDIS_URL"
        "MINIO_ENDPOINT"
        "MINIO_ACCESS_KEY"
        "MINIO_SECRET_KEY"
        "LITELLM_GATEWAY_URL"
    )
    
    MISSING_REQUIRED=()
    
    for var in "${REQUIRED_VARS[@]}"; do
        if [ -z "${!var}" ]; then
            MISSING_REQUIRED+=("$var")
            print_error "缺少必需环境变量: $var"
        else
            print_info "✓ $var"
        fi
    done
    
    for var in "${OPTIONAL_VARS[@]}"; do
        if [ -z "${!var}" ]; then
            print_info "○ $var (可选，未设置)"
        else
            print_info "✓ $var"
        fi
    done
    
    if [ ${#MISSING_REQUIRED[@]} -eq 0 ]; then
        print_success "所有必需环境变量已设置"
    else
        print_error "缺少 ${#MISSING_REQUIRED[@]} 个必需环境变量"
    fi
}

# ============================================================================
# 4. PostgreSQL 连接测试
# ============================================================================

check_postgresql() {
    print_header "检查 PostgreSQL 连接"
    
    if [ -z "$DATABASE_URL" ]; then
        print_warning "DATABASE_URL 未设置，跳过 PostgreSQL 检查"
        return
    fi
    
    print_info "测试数据库连接..."
    
    # 使用 Python 测试连接
    python3 << EOF
import sys
import os
try:
    import psycopg2
    from urllib.parse import urlparse
    
    db_url = os.environ.get('DATABASE_URL', '')
    if not db_url:
        print("DATABASE_URL 为空")
        sys.exit(1)
    
    # 解析 DATABASE_URL
    result = urlparse(db_url)
    conn = psycopg2.connect(
        database=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port or 5432
    )
    
    cursor = conn.cursor()
    cursor.execute('SELECT version();')
    version = cursor.fetchone()[0]
    print(f"PostgreSQL 版本: {version.split(',')[0]}")
    
    cursor.close()
    conn.close()
    sys.exit(0)
    
except ImportError:
    print("未安装 psycopg2-binary")
    sys.exit(1)
except Exception as e:
    print(f"连接失败: {e}")
    sys.exit(1)
EOF
    
    if [ $? -eq 0 ]; then
        print_success "PostgreSQL 连接正常"
    else
        print_error "PostgreSQL 连接失败"
    fi
}

# ============================================================================
# 5. Redis 连接测试（可选）
# ============================================================================

check_redis() {
    print_header "检查 Redis 连接（可选）"
    
    if [ -z "$REDIS_URL" ]; then
        print_info "REDIS_URL 未设置，跳过 Redis 检查"
        return
    fi
    
    print_info "测试 Redis 连接..."
    
    python3 << EOF
import sys
import os
try:
    import redis
    
    redis_url = os.environ.get('REDIS_URL', '')
    if not redis_url:
        print("REDIS_URL 为空")
        sys.exit(1)
    
    r = redis.from_url(redis_url)
    r.ping()
    info = r.info('server')
    print(f"Redis 版本: {info['redis_version']}")
    sys.exit(0)
    
except ImportError:
    print("未安装 redis")
    sys.exit(1)
except Exception as e:
    print(f"连接失败: {e}")
    sys.exit(1)
EOF
    
    if [ $? -eq 0 ]; then
        print_success "Redis 连接正常"
    else
        print_warning "Redis 连接失败（可选服务）"
    fi
}

# ============================================================================
# 6. MinIO 连接测试（可选）
# ============================================================================

check_minio() {
    print_header "检查 MinIO 连接（可选）"
    
    if [ -z "$MINIO_ENDPOINT" ] || [ -z "$MINIO_ACCESS_KEY" ] || [ -z "$MINIO_SECRET_KEY" ]; then
        print_info "MinIO 配置未完整设置，跳过 MinIO 检查"
        return
    fi
    
    print_info "测试 MinIO 连接..."
    
    python3 << EOF
import sys
import os
try:
    from minio import Minio
    
    endpoint = os.environ.get('MINIO_ENDPOINT', '')
    access_key = os.environ.get('MINIO_ACCESS_KEY', '')
    secret_key = os.environ.get('MINIO_SECRET_KEY', '')
    
    # 移除协议前缀
    endpoint = endpoint.replace('http://', '').replace('https://', '')
    
    client = Minio(
        endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=False
    )
    
    # 测试连接
    buckets = client.list_buckets()
    print(f"MinIO 连接成功，存储桶数量: {len(buckets)}")
    sys.exit(0)
    
except ImportError:
    print("未安装 minio")
    sys.exit(1)
except Exception as e:
    print(f"连接失败: {e}")
    sys.exit(1)
EOF
    
    if [ $? -eq 0 ]; then
        print_success "MinIO 连接正常"
    else
        print_warning "MinIO 连接失败（可选服务）"
    fi
}

# ============================================================================
# 7. 生成检查报告
# ============================================================================

generate_report() {
    if [ "$SILENT" = false ]; then
        print_header "环境检查总结"
        
        case $EXIT_CODE in
            0)
                echo -e "${GREEN}✓ 所有检查通过${NC}"
                ;;
            1)
                echo -e "${YELLOW}⚠ 存在警告，但可以继续运行${NC}"
                ;;
            2)
                echo -e "${RED}✗ 存在错误，请修复后再运行${NC}"
                ;;
        esac
        
        echo ""
        echo "详细信息请使用 --verbose 参数查看"
    fi
}

# ============================================================================
# 主函数
# ============================================================================

main() {
    if [ "$SILENT" = false ]; then
        echo -e "${BLUE}Velab 后端环境检查${NC}"
        echo ""
    fi
    
    check_python_version
    check_dependencies
    check_env_variables
    check_postgresql
    check_redis
    check_minio
    generate_report
    
    exit $EXIT_CODE
}

main
