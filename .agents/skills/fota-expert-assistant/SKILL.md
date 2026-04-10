---
name: fota-expert-assistant
description: FOTA (Firmware Over-The-Air) 诊断专家，擅长多域日志分析、ECU 状态机校验及历史工单智能关联。支持 iCGM/MPU/IVI/IPK 等核心控制器的固件升级全流程诊断。
---

# FOTA 专家诊断指令指南

当检测到用户正在处理 FOTA 升级失败、ECU 通信超时或下载校验错误等任务时，必须启用此辅助逻辑。

## 1. 核心状态机校验参考 (V2.0)
标准的 FOTA 升级流程应严格遵循以下序列。在分析日志时，请重点检查任何跳变或超时的步骤：
- **INIT**: 初始化环境，检查电量 (BATTERY_LEVEL >= 60%)。
- **VERSION_CHECK**: 云端比对版本及签名。
- **DOWNLOAD**: 固件下载 (HTTP Range 支持续传)。**常见风险点：网络波动导致断点数据错位。**
- **VERIFY**: SHA-256 完整性校验。**必须有校验成功日志。**
- **INSTALL**: ECU 分区写入。**关键监控 eMMC I/O 延迟及 UDS 响应。**
- **REBOOT**: A/B 分区切换。
- **COMPLETE**: 成果上报。

## 2. 常用 ECU 故障特征码
在阅读日志时，若遇到以下关键字，请立即关联相关诊断逻辑：
- `EMMC_WRITE_TIMEOUT`: 可能与 eMMC 磨损、高温 (>65°C) 或 NAND 性能退化有关。
- `CRC_MISMATCH`: 写入完成后分区数据校验失败，怀疑硬件干扰或存储坏块。
- `BATTERY_LOW_SAFETY`: 升级中电量跌破 50%，触发紧急回退。
- `DEPENDENCY_BROKEN`: 依赖链中断（如 iCGM 失败导致 MCU 挂起）。

## 3. 工具使用规范 (Tool Use Rules)
开发过程中应优先调用项目内置的 `services/` 工具层：
- **日志裁剪**：使用 `tool_functions.py:clip_log_by_time_window` 获取故障时刻前后的上下文。
- **相似度检索**：使用 `vector_search.py` 检索历史 Jira 工单 (tickets.json)。
- **切块逻辑**：如有大文档阅读需求，调用 `doc_chunker.py` 进行滑动窗口切块。

## 4. 如何执行评测框架 (Benchmarking)
要评估诊断性能，请运行以下指令并分析输出：
- `PYTHONPATH=./backend python3 backend/services/evaluation.py`
- 评分标准基于：关键词命中 (25%)、ECU 识别 (20%)、阶段检测 (20%)、RCA 相关度 (25%)、置信度 (10%)。

## 5. 设计约定与编码准则
- **诊断格式**：必须包含 `🎯 诊断结论`、`📊 详细分析`、`💡 修复建议` 和 `📚 证据来源` 四大板块。
- **代码规范**：所有异步逻辑需带 `trace_id` 追踪，由 `common/chain_log.py` 统一格式。
- **降级方案**：在无 API Key 的环境下，强制回退至 TF-IDF 检索基准。
