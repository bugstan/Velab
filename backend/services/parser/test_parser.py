"""
Parser Service 验证测试

简单的功能验证测试，确保Parser框架和解析器可以正常工作。

运行方式：
    python -m backend.services.parser.test_parser

作者：FOTA 诊断平台团队
创建时间：2026-04-03
"""

from pathlib import Path
from datetime import datetime
from io import StringIO
import tempfile

from .parser_android import AndroidParser
from .parser_fota import FotaParser
from .base import registry


def test_android_parser():
    """测试 Android 解析器"""
    print("\n=== 测试 Android 解析器 ===")
    
    # 创建测试日志内容
    test_log = """12-28 18:54:07.180  1234  5678 I FotaDownloadImpl: Download started
12-28 18:54:08.250  1234  5678 E FotaVerifyImpl: Signature verification failed
12-28 18:54:09.100  1234  5678 W FotaService: Retry attempt 1
12-28 18:54:10.500  1234  5678 I FotaService: Download complete
"""
    
    # 写入临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
        f.write(test_log)
        temp_path = Path(f.name)
    
    try:
        # 创建解析器并解析
        parser = AndroidParser()
        events = list(parser.parse_file(temp_path))
        
        print(f"✓ 成功解析 {len(events)} 个事件")
        
        # 验证解析结果
        assert len(events) == 4, f"期望4个事件，实际{len(events)}个"
        
        # 检查第一个事件
        event = events[0]
        assert event.source_type == "android"
        assert event.module == "FotaDownloadImpl"
        assert "Download started" in event.message
        assert event.level.value == "INFO"
        print(f"✓ 事件1: {event.module} - {event.message[:30]}...")
        
        # 检查错误事件
        error_event = events[1]
        assert error_event.level.value == "ERROR"
        assert "verification failed" in error_event.message
        print(f"✓ 事件2: {error_event.module} - {error_event.message[:30]}...")
        
        print("✓ Android 解析器测试通过")
        return True
        
    finally:
        # 清理临时文件
        temp_path.unlink()


def test_fota_parser():
    """测试 FOTA 解析器"""
    print("\n=== 测试 FOTA 解析器 ===")
    
    # 创建测试日志内容
    test_log = """2024-12-28 18:54:07.180 [INFO] [FotaDownloadImpl] Download started: version=1.2.3
2024-12-28 18:54:08.250 [ERROR] [FotaVerifyImpl] Signature verification failed: error code=0x1001
2024-12-28 18:54:09.100 [WARN] [FotaService] Retry attempt 1
2024-12-28 18:54:10.500 [INFO] [FotaInstallImpl] Installation progress: 45%
"""
    
    # 写入临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
        f.write(test_log)
        temp_path = Path(f.name)
    
    try:
        # 创建解析器并解析
        parser = FotaParser()
        events = list(parser.parse_file(temp_path))
        
        print(f"✓ 成功解析 {len(events)} 个事件")
        
        # 验证解析结果
        assert len(events) == 4, f"期望4个事件，实际{len(events)}个"
        
        # 检查第一个事件
        event = events[0]
        assert event.source_type == "fota"
        assert event.module == "FotaDownloadImpl"
        assert "version" in event.parsed_fields
        assert event.parsed_fields["version"] == "1.2.3"
        print(f"✓ 事件1: {event.module} - 版本={event.parsed_fields.get('version')}")
        
        # 检查错误事件
        error_event = events[1]
        assert error_event.level.value == "ERROR"
        assert "error_code" in error_event.parsed_fields
        assert error_event.parsed_fields["error_code"] == "1001"
        print(f"✓ 事件2: {error_event.module} - 错误码={error_event.parsed_fields.get('error_code')}")
        
        # 检查进度事件
        progress_event = events[3]
        assert "progress" in progress_event.parsed_fields
        assert progress_event.parsed_fields["progress"] == 45
        print(f"✓ 事件4: {progress_event.module} - 进度={progress_event.parsed_fields.get('progress')}%")
        
        print("✓ FOTA 解析器测试通过")
        return True
        
    finally:
        # 清理临时文件
        temp_path.unlink()


def test_time_window_filtering():
    """测试时间窗口过滤功能"""
    print("\n=== 测试时间窗口过滤 ===")
    
    # 创建测试日志内容（跨越多个时间点）
    test_log = """2024-12-28 18:50:00.000 [INFO] [FotaService] Event 1
2024-12-28 18:54:00.000 [INFO] [FotaService] Event 2
2024-12-28 18:55:00.000 [INFO] [FotaService] Event 3
2024-12-28 18:56:00.000 [INFO] [FotaService] Event 4
2024-12-28 19:00:00.000 [INFO] [FotaService] Event 5
"""
    
    # 写入临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
        f.write(test_log)
        temp_path = Path(f.name)
    
    try:
        parser = FotaParser()
        
        # 定义时间窗口：18:54:00 到 18:56:00
        time_window = (
            datetime(2024, 12, 28, 18, 54, 0),
            datetime(2024, 12, 28, 18, 56, 0)
        )
        
        # 使用时间窗口过滤
        events = list(parser.parse_file(temp_path, time_window=time_window))
        
        print(f"✓ 时间窗口过滤后剩余 {len(events)} 个事件")
        
        # 验证只有窗口内的事件被保留
        assert len(events) == 3, f"期望3个事件（Event 2,3,4），实际{len(events)}个"
        
        # 验证事件时间都在窗口内
        for event in events:
            assert time_window[0] <= event.original_ts <= time_window[1]
        
        print("✓ 时间窗口过滤测试通过")
        return True
        
    finally:
        # 清理临时文件
        temp_path.unlink()


def test_parser_registry():
    """测试解析器注册表"""
    print("\n=== 测试解析器注册表 ===")
    
    # 检查注册的解析器
    supported_types = registry.list_supported_types()
    print(f"✓ 已注册的解析器类型: {supported_types}")
    
    assert "android" in supported_types
    assert "fota" in supported_types
    
    # 获取解析器实例
    android_parser = registry.get_parser("android")
    assert android_parser is not None
    assert android_parser.source_type == "android"
    print(f"✓ 成功获取 Android 解析器: {android_parser.parser_name}")
    
    fota_parser = registry.get_parser("fota")
    assert fota_parser is not None
    assert fota_parser.source_type == "fota"
    print(f"✓ 成功获取 FOTA 解析器: {fota_parser.parser_name}")
    
    # 测试不存在的解析器
    unknown_parser = registry.get_parser("unknown")
    assert unknown_parser is None
    print("✓ 不存在的解析器正确返回 None")
    
    print("✓ 解析器注册表测试通过")
    return True


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("Parser Service 验证测试")
    print("=" * 60)
    
    tests = [
        ("Android 解析器", test_android_parser),
        ("FOTA 解析器", test_fota_parser),
        ("时间窗口过滤", test_time_window_filtering),
        ("解析器注册表", test_parser_registry),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"✗ {test_name} 测试失败: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_all_tests()
    sys.exit(0 if success else 1)
