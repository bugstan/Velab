---
description: 评估 FOTA 后端诊断性能（一键运行测试集并生成报告）
---

1. 进入工作区根目录
// turbo
2. 运行 FOTA 评测框架
```bash
PYTHONPATH=./backend python3 backend/services/evaluation.py
```
3. 分析结果报告
   - 检查 `total_cases` 是否全部覆盖
   - 检查加权总分 `total_score` 是否达到 0.6 阈值
   - 针对失败案例，调用 `fota-expert-assistant` 的 `SKILL.md` 的分析指令。
4. 归档评测结果到 `data/eval/reports/` (如果需要)
