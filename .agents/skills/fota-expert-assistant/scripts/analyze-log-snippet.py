#!/usr/bin/env python3
"""
FOTA 日志分段秒扫脚本 (Skill Helper)
快速提取 FOTA 阶段变更及关联的关键错误码
"""
import sys
import re

STAGES = ["INIT", "DOWNLOAD", "VERIFY", "INSTALL", "REBOOT", "COMPLETE"]
ERRORS = ["EMMC_WRITE_TIMEOUT", "CRC_MISMATCH", "BATTERY_LOW", "DEPENDENCY_BROKEN", "DOWNLOAD_PAUSED", "PACKAGE_VERIFY_FAILED"]

def analyze(log_path):
    print(f"--- FOTA 日志分析摘要: {log_path} ---")
    
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        
    # 统计阶段
    found_stages = []
    for s in STAGES:
        if s in content:
            found_stages.append(s)
    
    print(f"已识别到的升级阶段: {' -> '.join(found_stages) if found_stages else '未检测到标准阶段'}")
    
    # 扫描致命错误
    found_errors = []
    for e in ERRORS:
        matches = re.finditer(rf".*{e}.*", content)
        for m in matches:
            found_errors.append(m.group(0).strip())
            
    if found_errors:
        print("\n[🚨 关键错误检测]")
        for fe in set(found_errors):
            print(f"- {fe}")
    else:
        print("\n[✅ 未发现致命错误码]")
        
    print("\n[🔎 关联修复建议]: 请参考项目文档 docs/TODO.md 或历史工单 FOTA - [ID] 库。")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 analyze-log-snippet.py <log_file>")
        sys.exit(1)
    analyze(sys.argv[1])
