"""
测试新增的5个解析器
运行方式: cd backend/services/parser && python3 test_new_parsers.py
"""

import unittest
import sys
from datetime import datetime

# 导入解析器（使用相对导入的替代方案）
try:
    from parser_kernel import KernelParser
    from parser_mcu import MCUParser
    from parser_dlt import DLTParser
    from parser_ibdu import IBDUParser
    from parser_vehicle_signal import VehicleSignalParser
    from base import EventLevel, EventType, ParserRegistry
    from parser_android import AndroidParser
    from parser_fota import FotaParser
except ImportError:
    # 如果相对导入失败，尝试添加路径
    import os
    sys.path.insert(0, os.path.dirname(__file__))
    from parser_kernel import KernelParser
    from parser_mcu import MCUParser
    from parser_dlt import DLTParser
    from parser_ibdu import IBDUParser
    from parser_vehicle_signal import VehicleSignalParser
    from base import EventLevel, EventType, ParserRegistry
    from parser_android import AndroidParser
    from parser_fota import FotaParser


class TestKernelParser(unittest.TestCase):
    
    def setUp(self):
        self.parser = KernelParser()
    
    def test_parse_kernel_log(self):
        """测试kernel log解析"""
        line = '[  123.456789] <6>[ T1234] usb 1-1: new high-speed USB device'
        event = self.parser.parse_line(line, 1)
        
        self.assertIsNotNone(event)
        self.assertEqual(event.source_type, 'kernel')
        self.assertEqual(event.level, EventLevel.INFO)
        self.assertIn('usb', event.message.lower())
    
    def test_parse_kernel_panic(self):
        """测试kernel panic识别"""
        line = '[  456.789012] <0>[ T5678] Kernel panic - not syncing: Fatal exception'
        event = self.parser.parse_line(line, 1)
        
        self.assertIsNotNone(event)
        self.assertEqual(event.level, EventLevel.FATAL)
        self.assertEqual(event.event_type, EventType.ERROR)


class TestMCUParser(unittest.TestCase):
    
    def setUp(self):
        self.parser = MCUParser()
    
    def test_parse_mcu_format1(self):
        """测试MCU格式1"""
        line = '[12345] [INFO] [POWER] Battery voltage normal'
        event = self.parser.parse_line(line, 1)
        
        self.assertIsNotNone(event)
        self.assertEqual(event.source_type, 'mcu')
        self.assertEqual(event.level, EventLevel.INFO)
        self.assertEqual(event.module, 'POWER')
        self.assertIn('uptime_seconds', event.parsed_fields)
    
    def test_parse_mcu_format2(self):
        """测试MCU格式2"""
        line = '12345.678 E FOTA: Update failed'
        event = self.parser.parse_line(line, 1)
        
        self.assertIsNotNone(event)
        self.assertEqual(event.level, EventLevel.ERROR)
        self.assertEqual(event.module, 'FOTA')
        self.assertEqual(event.event_type, EventType.FOTA_STAGE)
    
    def test_parse_mcu_format3(self):
        """测试MCU格式3"""
        line = '+5000ms [CAN] Message received'
        event = self.parser.parse_line(line, 1)
        
        self.assertIsNotNone(event)
        self.assertEqual(event.module, 'CAN')
        self.assertIn('uptime_ms', event.parsed_fields)


class TestDLTParser(unittest.TestCase):
    
    def setUp(self):
        self.parser = DLTParser()
    
    def test_parse_dlt_full_format(self):
        """测试完整DLT格式"""
        line = '2024/01/01 10:00:00.123456 123456 ECU1 APP1 CTX1 log info V 1 [Test message]'
        event = self.parser.parse_line(line, 1)
        
        self.assertIsNotNone(event)
        self.assertEqual(event.source_type, 'dlt')
        self.assertEqual(event.level, EventLevel.INFO)
        self.assertEqual(event.module, 'APP1.CTX1')
        self.assertIn('ecu_id', event.parsed_fields)
        self.assertEqual(event.parsed_fields['ecu_id'], 'ECU1')
    
    def test_parse_dlt_simple_format(self):
        """测试简化DLT格式"""
        line = '2024-01-01 10:00:00.123 [FOTA] [ERROR] Update failed'
        event = self.parser.parse_line(line, 1)
        
        self.assertIsNotNone(event)
        self.assertEqual(event.level, EventLevel.ERROR)
        self.assertEqual(event.module, 'FOTA')


class TestIBDUParser(unittest.TestCase):
    
    def setUp(self):
        self.parser = IBDUParser()
    
    def test_parse_ibdu_with_voltage(self):
        """测试iBDU电压解析"""
        line = '2024-01-01 10:00:00.123 [POWER] INFO: Battery voltage: 12.5V'
        event = self.parser.parse_line(line, 1)
        
        self.assertIsNotNone(event)
        self.assertEqual(event.source_type, 'ibdu')
        self.assertEqual(event.module, 'POWER')
        self.assertEqual(event.event_type, EventType.SYSTEM)
        self.assertIn('voltage', event.parsed_fields)
        self.assertEqual(event.parsed_fields['voltage'], 12.5)
    
    def test_parse_ibdu_with_current(self):
        """测试iBDU电流解析"""
        line = '2024-01-01 10:00:00 INFO Battery current: 5.2A'
        event = self.parser.parse_line(line, 1)
        
        self.assertIsNotNone(event)
        self.assertIn('current', event.parsed_fields)
        self.assertEqual(event.parsed_fields['current'], 5.2)
    
    def test_parse_ibdu_with_temperature(self):
        """测试iBDU温度解析"""
        line = '2024-01-01 10:00:00 WARN Temperature high: 85°C'
        event = self.parser.parse_line(line, 1)
        
        self.assertIsNotNone(event)
        self.assertEqual(event.level, EventLevel.WARN)
        self.assertIn('temperature', event.parsed_fields)
        self.assertEqual(event.parsed_fields['temperature'], 85.0)


class TestVehicleSignalParser(unittest.TestCase):
    
    def setUp(self):
        self.parser = VehicleSignalParser()
    
    def test_parse_csv_format(self):
        """测试CSV格式"""
        line = '2024-01-01 10:00:00.123,VehicleSpeed,60.5,km/h'
        event = self.parser.parse_line(line, 2)  # line 2 (skip header)
        
        self.assertIsNotNone(event)
        self.assertEqual(event.source_type, 'vehicle_signal')
        self.assertIn('signal_name', event.parsed_fields)
        self.assertEqual(event.parsed_fields['signal_name'], 'VehicleSpeed')
        self.assertEqual(event.parsed_fields['value'], 60.5)
        self.assertEqual(event.parsed_fields['unit'], 'km/h')
    
    def test_parse_table_format(self):
        """测试表格格式"""
        line = '2024-01-01 10:00:00 | EngineSpeed | 3000 | rpm'
        event = self.parser.parse_line(line, 2)
        
        self.assertIsNotNone(event)
        self.assertEqual(event.parsed_fields['signal_name'], 'EngineSpeed')
        self.assertEqual(event.parsed_fields['value'], 3000.0)
    
    def test_voltage_warning(self):
        """测试电压异常检测"""
        line = '2024-01-01 10:00:00,BatteryVoltage,10.5,V'
        event = self.parser.parse_line(line, 2)
        
        self.assertIsNotNone(event)
        self.assertEqual(event.level, EventLevel.WARN)  # 低于11V
    
    def test_critical_signal(self):
        """测试关键信号标记"""
        line = '2024-01-01 10:00:00,VehicleSpeed,120,km/h'
        event = self.parser.parse_line(line, 2)
        
        self.assertIsNotNone(event)
        self.assertTrue(event.parsed_fields['is_critical'])


class TestParserRegistry(unittest.TestCase):
    
    def test_all_parsers_registered(self):
        """测试所有解析器都已注册"""
        # 注册所有解析器(注册类而不是实例)
        registry = ParserRegistry()
        registry.register('android', AndroidParser)
        registry.register('fota', FotaParser)
        registry.register('kernel', KernelParser)
        registry.register('mcu', MCUParser)
        registry.register('dlt', DLTParser)
        registry.register('ibdu', IBDUParser)
        registry.register('vehicle_signal', VehicleSignalParser)
        
        # 验证所有7个解析器都已注册
        self.assertEqual(len(registry._parsers), 7)
        
        # 验证可以获取每个解析器
        for parser_type in ['android', 'fota', 'kernel', 'mcu', 'dlt', 'ibdu', 'vehicle_signal']:
            parser = registry.get_parser(parser_type)
            self.assertIsNotNone(parser, f"Parser {parser_type} not found")


if __name__ == '__main__':
    # 运行测试
    unittest.main(verbosity=2)
