#!/bin/bash
# ============================================================================
# Velab FOTA 诊断系统 - MinIO 初始化脚本
# ============================================================================
# 用途：初始化 MinIO 存储桶、设置访问策略、测试连接
# 使用：./init_minio.sh [--endpoint ENDPOINT] [--verbose]
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
        --endpoint)
            MINIO_ENDPOINT="$2"
            shift 2
            ;;
        --access-key)
            MINIO_ACCESS_KEY="$2"
            shift 2
            ;;
        --secret-key)
            MINIO_SECRET_KEY="$2"
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
            echo "  --endpoint URL       MinIO 端点（默认从 .env 读取）"
            echo "  --access-key KEY     访问密钥（默认从 .env 读取）"
            echo "  --secret-key KEY     秘密密钥（默认从 .env 读取）"
            echo "  --verbose, -v        显示详细信息"
            echo "  --help, -h           显示此帮助信息"
            echo ""
            echo "示例:"
            echo "  $0"
            echo "  $0 --endpoint localhost:9000"
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

if [ -f "$BACKEND_DIR/.env" ]; then
    print_info "从 .env 文件加载配置"
    set -a
    source "$BACKEND_DIR/.env"
    set +a
fi

# 验证必需参数
if [ -z "$MINIO_ENDPOINT" ]; then
    print_error "MINIO_ENDPOINT 未设置"
    echo "请设置环境变量或使用 --endpoint 参数"
    exit 1
fi

if [ -z "$MINIO_ACCESS_KEY" ]; then
    print_error "MINIO_ACCESS_KEY 未设置"
    echo "请设置环境变量或使用 --access-key 参数"
    exit 1
fi

if [ -z "$MINIO_SECRET_KEY" ]; then
    print_error "MINIO_SECRET_KEY 未设置"
    echo "请设置环境变量或使用 --secret-key 参数"
    exit 1
fi

# ============================================================================
# MinIO 初始化
# ============================================================================

init_minio() {
    print_header "初始化 MinIO"
    
    print_info "MinIO Endpoint: $MINIO_ENDPOINT"
    
    python3 << EOF
import sys
import os
import json
from datetime import datetime

try:
    from minio import Minio
    from minio.error import S3Error
except ImportError:
    print("错误: 未安装 minio 包")
    print("请运行: pip install minio")
    sys.exit(1)

# 获取配置
endpoint = os.environ.get('MINIO_ENDPOINT', '')
access_key = os.environ.get('MINIO_ACCESS_KEY', '')
secret_key = os.environ.get('MINIO_SECRET_KEY', '')

# 移除协议前缀
endpoint = endpoint.replace('http://', '').replace('https://', '')
secure = False  # 开发环境使用 HTTP

print(f"连接到 MinIO: {endpoint}")

try:
    client = Minio(
        endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure
    )
    
    # 测试连接
    client.list_buckets()
    print("✓ MinIO 连接成功")
    
except Exception as e:
    print(f"✗ MinIO 连接失败: {e}")
    sys.exit(1)

# ============================================================================
# 1. 创建存储桶
# ============================================================================
print("\n创建存储桶...")

BUCKETS = {
    'raw-logs': {
        'description': '原始日志文件存储',
        'versioning': False,
    },
    'processed-logs': {
        'description': '处理后的日志文件存储',
        'versioning': False,
    },
    'fota-packages': {
        'description': 'FOTA 升级包存储',
        'versioning': True,
    },
    'reports': {
        'description': '分析报告存储',
        'versioning': False,
    },
}

created_buckets = []
existing_buckets = []

for bucket_name, config in BUCKETS.items():
    try:
        if client.bucket_exists(bucket_name):
            print(f"  ○ 存储桶已存在: {bucket_name}")
            existing_buckets.append(bucket_name)
        else:
            client.make_bucket(bucket_name)
            print(f"  ✓ 创建存储桶: {bucket_name} - {config['description']}")
            created_buckets.append(bucket_name)
            
    except S3Error as e:
        print(f"  ✗ 创建存储桶失败 {bucket_name}: {e}")
        sys.exit(1)

print(f"\n✓ 创建 {len(created_buckets)} 个新存储桶，{len(existing_buckets)} 个已存在")

# ============================================================================
# 2. 设置访问策略
# ============================================================================
print("\n设置访问策略...")

# 公共读策略（用于报告下载）
public_read_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"AWS": "*"},
            "Action": ["s3:GetObject"],
            "Resource": ["arn:aws:s3:::reports/*"]
        }
    ]
}

try:
    client.set_bucket_policy('reports', json.dumps(public_read_policy))
    print("  ✓ reports: 公共读访问")
except Exception as e:
    print(f"  ⚠ 设置策略失败 (reports): {e}")

# 私有策略（默认）
for bucket_name in ['raw-logs', 'processed-logs', 'fota-packages']:
    print(f"  ✓ {bucket_name}: 私有访问（默认）")

print("✓ 访问策略设置完成")

# ============================================================================
# 3. 测试上传和下载
# ============================================================================
print("\n测试基本操作...")

test_bucket = 'raw-logs'
test_object = 'test/connection_test.txt'
test_content = f'MinIO 连接测试 - {datetime.utcnow().isoformat()}'

try:
    # 测试上传
    from io import BytesIO
    data = BytesIO(test_content.encode('utf-8'))
    client.put_object(
        test_bucket,
        test_object,
        data,
        length=len(test_content),
        content_type='text/plain'
    )
    print(f"  ✓ 上传测试文件: {test_object}")
    
    # 测试下载
    response = client.get_object(test_bucket, test_object)
    downloaded_content = response.read().decode('utf-8')
    response.close()
    response.release_conn()
    
    if downloaded_content == test_content:
        print(f"  ✓ 下载测试文件: 内容匹配")
    else:
        print(f"  ✗ 下载测试文件: 内容不匹配")
        sys.exit(1)
    
    # 测试删除
    client.remove_object(test_bucket, test_object)
    print(f"  ✓ 删除测试文件")
    
except Exception as e:
    print(f"  ✗ 基本操作测试失败: {e}")
    sys.exit(1)

print("✓ 基本操作测试通过")

# ============================================================================
# 4. 创建目录结构
# ============================================================================
print("\n创建目录结构...")

DIRECTORY_STRUCTURE = {
    'raw-logs': ['daily/', 'hourly/', 'archive/'],
    'processed-logs': ['analysis/', 'summary/', 'archive/'],
    'fota-packages': ['stable/', 'beta/', 'archive/'],
    'reports': ['daily/', 'weekly/', 'monthly/'],
}

for bucket_name, directories in DIRECTORY_STRUCTURE.items():
    for directory in directories:
        try:
            # MinIO 使用空对象创建"目录"
            client.put_object(
                bucket_name,
                directory + '.keep',
                BytesIO(b''),
                length=0
            )
            print(f"  ✓ {bucket_name}/{directory}")
        except Exception as e:
            print(f"  ⚠ 创建目录失败 {bucket_name}/{directory}: {e}")

print("✓ 目录结构创建完成")

# ============================================================================
# 5. 显示 MinIO 信息
# ============================================================================
print("\n" + "="*40)
print("MinIO 信息")
print("="*40)

buckets = client.list_buckets()
print(f"存储桶总数: {len(buckets)}")
print("\n存储桶列表:")

for bucket in buckets:
    if bucket.name in BUCKETS:
        try:
            # 获取存储桶中的对象数量
            objects = list(client.list_objects(bucket.name, recursive=True))
            size = sum(obj.size for obj in objects if obj.size)
            print(f"  • {bucket.name}")
            print(f"    - 创建时间: {bucket.creation_date}")
            print(f"    - 对象数量: {len(objects)}")
            print(f"    - 总大小: {size} bytes")
        except Exception as e:
            print(f"  • {bucket.name} (无法获取详细信息)")

print("\n✓ MinIO 初始化完成")
sys.exit(0)
EOF

    if [ $? -eq 0 ]; then
        print_success "MinIO 初始化成功"
        return 0
    else
        print_error "MinIO 初始化失败"
        return 1
    fi
}

# ============================================================================
# 主函数
# ============================================================================

main() {
    echo -e "${BLUE}Velab MinIO 初始化${NC}"
    echo ""
    
    if init_minio; then
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
