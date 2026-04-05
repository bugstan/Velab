#!/bin/bash
# ============================================================================
# Velab FOTA 诊断系统 - LiteLLM 配置验证脚本
# ============================================================================
# 用途：验证 LiteLLM config.yaml 语法、环境变量和 API Keys
# 使用：./validate_config.sh [--config CONFIG_FILE] [--verbose]
# 退出码：0=成功，1=警告，2=错误
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
EXIT_CODE=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATEWAY_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$GATEWAY_DIR/config.yaml"

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

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
    [ $EXIT_CODE -lt 1 ] && EXIT_CODE=1
}

print_error() {
    echo -e "${RED}✗${NC} $1" >&2
    EXIT_CODE=2
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
        --config|-c)
            CONFIG_FILE="$2"
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
            echo "  --config, -c FILE    配置文件路径（默认: gateway/config.yaml）"
            echo "  --verbose, -v        显示详细信息"
            echo "  --help, -h           显示此帮助信息"
            echo ""
            echo "退出码:"
            echo "  0  配置验证通过"
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
# 1. 检查配置文件存在性
# ============================================================================

check_config_exists() {
    print_header "检查配置文件"
    
    if [ ! -f "$CONFIG_FILE" ]; then
        print_error "配置文件不存在: $CONFIG_FILE"
        return 1
    fi
    
    print_success "配置文件存在: $CONFIG_FILE"
    print_info "文件大小: $(stat -f%z "$CONFIG_FILE" 2>/dev/null || stat -c%s "$CONFIG_FILE" 2>/dev/null) bytes"
    return 0
}

# ============================================================================
# 2. 验证 YAML 语法
# ============================================================================

validate_yaml_syntax() {
    print_header "验证 YAML 语法"
    
    python3 << EOF
import sys
import yaml

try:
    with open('$CONFIG_FILE', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    if config is None:
        print("✗ 配置文件为空")
        sys.exit(1)
    
    print("✓ YAML 语法正确")
    print(f"  配置项数量: {len(config) if isinstance(config, dict) else 'N/A'}")
    sys.exit(0)
    
except yaml.YAMLError as e:
    print(f"✗ YAML 语法错误: {e}")
    sys.exit(1)
except Exception as e:
    print(f"✗ 读取配置文件失败: {e}")
    sys.exit(1)
EOF

    if [ $? -eq 0 ]; then
        print_success "YAML 语法验证通过"
        return 0
    else
        print_error "YAML 语法验证失败"
        return 1
    fi
}

# ============================================================================
# 3. 验证配置结构
# ============================================================================

validate_config_structure() {
    print_header "验证配置结构"
    
    python3 << EOF
import sys
import yaml
import os

try:
    with open('$CONFIG_FILE', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    errors = []
    warnings = []
    
    # 检查必需的顶级字段
    required_fields = ['model_list']
    for field in required_fields:
        if field not in config:
            errors.append(f"缺少必需字段: {field}")
        else:
            print(f"✓ 必需字段存在: {field}")
    
    # 检查 model_list
    if 'model_list' in config:
        model_list = config['model_list']
        
        if not isinstance(model_list, list):
            errors.append("model_list 必须是列表类型")
        elif len(model_list) == 0:
            warnings.append("model_list 为空，未配置任何模型")
        else:
            print(f"  模型数量: {len(model_list)}")
            
            # 验证每个模型配置
            for idx, model in enumerate(model_list):
                model_name = model.get('model_name', f'model_{idx}')
                
                # 检查必需字段
                required_model_fields = ['model_name', 'litellm_params']
                for field in required_model_fields:
                    if field not in model:
                        errors.append(f"模型 {model_name}: 缺少字段 {field}")
                
                # 检查 litellm_params
                if 'litellm_params' in model:
                    params = model['litellm_params']
                    
                    if 'model' not in params:
                        errors.append(f"模型 {model_name}: litellm_params 缺少 model 字段")
                    
                    if 'api_key' in params:
                        api_key = params['api_key']
                        if api_key.startswith('os.environ/'):
                            env_var = api_key.replace('os.environ/', '')
                            if not os.environ.get(env_var):
                                warnings.append(f"模型 {model_name}: 环境变量 {env_var} 未设置")
                        elif api_key.startswith('sk-') or len(api_key) > 20:
                            print(f"  ✓ 模型 {model_name}: API Key 已配置")
                        else:
                            warnings.append(f"模型 {model_name}: API Key 格式可能不正确")
    
    # 检查可选配置
    optional_fields = {
        'general_settings': '通用设置',
        'litellm_settings': 'LiteLLM 设置',
        'router_settings': '路由设置',
    }
    
    for field, desc in optional_fields.items():
        if field in config:
            print(f"  ○ 可选字段存在: {field} ({desc})")
    
    # 输出结果
    if errors:
        print("\n错误:")
        for error in errors:
            print(f"  ✗ {error}")
    
    if warnings:
        print("\n警告:")
        for warning in warnings:
            print(f"  ⚠ {warning}")
    
    if errors:
        sys.exit(2)
    elif warnings:
        sys.exit(1)
    else:
        print("\n✓ 配置结构验证通过")
        sys.exit(0)
    
except Exception as e:
    print(f"✗ 配置验证失败: {e}")
    sys.exit(2)
EOF

    local result=$?
    if [ $result -eq 0 ]; then
        print_success "配置结构验证通过"
        return 0
    elif [ $result -eq 1 ]; then
        print_warning "配置结构存在警告"
        return 0
    else
        print_error "配置结构验证失败"
        return 1
    fi
}

# ============================================================================
# 4. 检查环境变量
# ============================================================================

check_environment_variables() {
    print_header "检查环境变量"
    
    # 加载 .env 文件
    if [ -f "$GATEWAY_DIR/.env" ]; then
        print_info "加载 .env 文件"
        set -a
        source "$GATEWAY_DIR/.env"
        set +a
    else
        print_warning "未找到 .env 文件"
    fi
    
    python3 << EOF
import sys
import yaml
import os
import re

try:
    with open('$CONFIG_FILE', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 提取所有环境变量引用
    env_vars = set()
    
    def extract_env_vars(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, str) and value.startswith('os.environ/'):
                    env_var = value.replace('os.environ/', '')
                    env_vars.add(env_var)
                else:
                    extract_env_vars(value)
        elif isinstance(obj, list):
            for item in obj:
                extract_env_vars(item)
    
    extract_env_vars(config)
    
    if not env_vars:
        print("  ○ 配置中未使用环境变量")
        sys.exit(0)
    
    print(f"  发现 {len(env_vars)} 个环境变量引用")
    
    missing_vars = []
    set_vars = []
    
    for var in sorted(env_vars):
        if os.environ.get(var):
            set_vars.append(var)
            print(f"  ✓ {var}")
        else:
            missing_vars.append(var)
            print(f"  ✗ {var} (未设置)")
    
    if missing_vars:
        print(f"\n⚠ {len(missing_vars)} 个环境变量未设置")
        sys.exit(1)
    else:
        print(f"\n✓ 所有环境变量已设置")
        sys.exit(0)
    
except Exception as e:
    print(f"✗ 环境变量检查失败: {e}")
    sys.exit(2)
EOF

    local result=$?
    if [ $result -eq 0 ]; then
        print_success "环境变量检查通过"
        return 0
    elif [ $result -eq 1 ]; then
        print_warning "部分环境变量未设置"
        return 0
    else
        print_error "环境变量检查失败"
        return 1
    fi
}

# ============================================================================
# 5. 验证 API Keys 格式
# ============================================================================

validate_api_keys() {
    print_header "验证 API Keys 格式"
    
    python3 << EOF
import sys
import yaml
import os
import re

try:
    with open('$CONFIG_FILE', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    if 'model_list' not in config:
        print("  ○ 未配置模型")
        sys.exit(0)
    
    warnings = []
    validated = []
    
    for model in config['model_list']:
        model_name = model.get('model_name', 'unknown')
        
        if 'litellm_params' not in model:
            continue
        
        params = model['litellm_params']
        api_key = params.get('api_key', '')
        
        if not api_key:
            warnings.append(f"模型 {model_name}: 未配置 API Key")
            continue
        
        # 解析环境变量
        if api_key.startswith('os.environ/'):
            env_var = api_key.replace('os.environ/', '')
            api_key = os.environ.get(env_var, '')
            
            if not api_key:
                warnings.append(f"模型 {model_name}: 环境变量 {env_var} 未设置")
                continue
        
        # 验证 API Key 格式
        provider = params.get('model', '').split('/')[0] if '/' in params.get('model', '') else ''
        
        # OpenAI 格式: sk-...
        if provider in ['openai', 'azure'] or api_key.startswith('sk-'):
            if api_key.startswith('sk-') and len(api_key) > 20:
                validated.append(f"模型 {model_name}: OpenAI 格式")
            else:
                warnings.append(f"模型 {model_name}: API Key 格式可能不正确")
        
        # Anthropic 格式: sk-ant-...
        elif api_key.startswith('sk-ant-'):
            if len(api_key) > 30:
                validated.append(f"模型 {model_name}: Anthropic 格式")
            else:
                warnings.append(f"模型 {model_name}: API Key 格式可能不正确")
        
        # 其他格式
        elif len(api_key) > 10:
            validated.append(f"模型 {model_name}: 自定义格式")
        else:
            warnings.append(f"模型 {model_name}: API Key 长度过短")
    
    # 输出结果
    if validated:
        print("验证通过:")
        for item in validated:
            print(f"  ✓ {item}")
    
    if warnings:
        print("\n警告:")
        for warning in warnings:
            print(f"  ⚠ {warning}")
        sys.exit(1)
    else:
        print(f"\n✓ 所有 API Keys 格式正确")
        sys.exit(0)
    
except Exception as e:
    print(f"✗ API Keys 验证失败: {e}")
    sys.exit(2)
EOF

    local result=$?
    if [ $result -eq 0 ]; then
        print_success "API Keys 验证通过"
        return 0
    elif [ $result -eq 1 ]; then
        print_warning "API Keys 存在警告"
        return 0
    else
        print_error "API Keys 验证失败"
        return 1
    fi
}

# ============================================================================
# 6. 生成验证报告
# ============================================================================

generate_report() {
    print_header "配置验证总结"
    
    case $EXIT_CODE in
        0)
            echo -e "${GREEN}✓ 配置验证通过，可以启动服务${NC}"
            ;;
        1)
            echo -e "${YELLOW}⚠ 配置存在警告，建议检查后再启动${NC}"
            ;;
        2)
            echo -e "${RED}✗ 配置存在错误，请修复后再启动${NC}"
            ;;
    esac
}

# ============================================================================
# 主函数
# ============================================================================

main() {
    echo -e "${BLUE}Velab LiteLLM 配置验证${NC}"
    echo ""
    
    check_config_exists || exit 2
    validate_yaml_syntax || exit 2
    validate_config_structure
    check_environment_variables
    validate_api_keys
    generate_report
    
    exit $EXIT_CODE
}

main
