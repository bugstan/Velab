"""
测试运行脚本

运行所有API测试
"""

import sys
import pytest


def main():
    """运行测试"""
    # pytest参数
    args = [
        "tests/",                    # 测试目录
        "-v",                        # 详细输出
        "--tb=short",                # 简短的traceback
        "--strict-markers",          # 严格标记模式
        "-p", "no:warnings",         # 禁用警告
        "--color=yes",               # 彩色输出
    ]
    
    # 如果有命令行参数，添加到pytest参数中
    if len(sys.argv) > 1:
        args.extend(sys.argv[1:])
    
    # 运行pytest
    exit_code = pytest.main(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
