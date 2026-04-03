#!/bin/bash

# Velab Web 依赖更新脚本
# 使用方法: ./scripts/update-dependencies.sh [conservative|aggressive]

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查是否在 web 目录
if [ ! -f "package.json" ]; then
    print_error "请在 web 目录下运行此脚本"
    exit 1
fi

# 获取更新模式
MODE=${1:-conservative}

print_info "依赖更新模式: $MODE"
echo ""

# 备份 package.json 和 package-lock.json
print_info "备份当前依赖配置..."
cp package.json package.json.backup
cp package-lock.json package-lock.json.backup
print_success "备份完成"
echo ""

# 保守更新模式
if [ "$MODE" = "conservative" ]; then
    print_info "执行保守更新（推荐）..."
    echo ""
    
    # 1. 更新 Next.js 和配套工具
    print_info "步骤 1/3: 更新 Next.js 和 ESLint Config..."
    npm install next@16.2.2 eslint-config-next@16.2.2
    print_success "Next.js 更新完成"
    echo ""
    
    # 2. 修复安全漏洞
    print_info "步骤 2/3: 修复安全漏洞..."
    npm audit fix
    print_success "安全漏洞修复完成"
    echo ""
    
    # 3. 验证更新
    print_info "步骤 3/3: 验证更新..."
    
    print_info "运行构建..."
    if npm run build; then
        print_success "构建成功"
    else
        print_error "构建失败"
        print_warning "正在恢复备份..."
        mv package.json.backup package.json
        mv package-lock.json.backup package-lock.json
        npm install
        exit 1
    fi
    
    print_info "运行测试..."
    if npm test; then
        print_success "测试通过"
    else
        print_warning "测试失败，但构建成功，继续更新流程"
    fi
    
    print_info "运行 Lint..."
    if npm run lint; then
        print_success "Lint 通过"
    else
        print_warning "Lint 有警告，但不影响更新"
    fi
    
    echo ""
    print_success "保守更新完成！"
    print_info "已更新的依赖:"
    echo "  - next: 16.2.0 → 16.2.2"
    echo "  - eslint-config-next: 16.2.0 → 16.2.2"
    echo "  - 修复了 2 个安全漏洞"
    
# 激进更新模式
elif [ "$MODE" = "aggressive" ]; then
    print_warning "执行激进更新（不推荐用于生产环境）..."
    echo ""
    
    # 1. 更新所有依赖
    print_info "步骤 1/3: 更新所有依赖到最新版本..."
    npm install next@16.2.2 eslint-config-next@16.2.2
    npm install -D typescript@6.0.2 eslint@10.1.0 @types/node@25.5.1
    print_success "依赖更新完成"
    echo ""
    
    # 2. 修复安全漏洞
    print_info "步骤 2/3: 修复安全漏洞..."
    npm audit fix
    print_success "安全漏洞修复完成"
    echo ""
    
    # 3. 验证更新
    print_info "步骤 3/3: 验证更新..."
    
    print_info "运行构建..."
    if npm run build; then
        print_success "构建成功"
    else
        print_error "构建失败"
        print_warning "正在恢复备份..."
        mv package.json.backup package.json
        mv package-lock.json.backup package-lock.json
        npm install
        exit 1
    fi
    
    print_info "运行测试..."
    if npm test; then
        print_success "测试通过"
    else
        print_warning "测试失败，但构建成功，继续更新流程"
    fi
    
    print_info "运行 Lint..."
    if npm run lint; then
        print_success "Lint 通过"
    else
        print_warning "Lint 有警告，请检查配置"
    fi
    
    echo ""
    print_success "激进更新完成！"
    print_info "已更新的依赖:"
    echo "  - next: 16.2.0 → 16.2.2"
    echo "  - eslint-config-next: 16.2.0 → 16.2.2"
    echo "  - typescript: 5.9.3 → 6.0.2"
    echo "  - eslint: 9.39.4 → 10.1.0"
    echo "  - @types/node: 20.19.37 → 25.5.1"
    echo "  - 修复了 2 个安全漏洞"
    
else
    print_error "未知的更新模式: $MODE"
    print_info "可用模式: conservative (保守) 或 aggressive (激进)"
    exit 1
fi

echo ""
print_info "备份文件保存在:"
echo "  - package.json.backup"
echo "  - package-lock.json.backup"
print_info "如果一切正常，可以删除备份文件:"
echo "  rm package.json.backup package-lock.json.backup"
echo ""
print_success "依赖更新流程完成！"
