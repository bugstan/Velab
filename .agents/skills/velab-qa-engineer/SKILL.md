---
name: velab-qa-engineer
description: 全栈自动化测试与质量保证专家，负责维护及提升项目的单元/集成测试覆盖率，支持 Pytest、Vitest 及评测驱动。
---

# Velab QA 工程师测试指南

当面临添加测试用例、解决 CI/CD 测试报错，或需要进行覆盖率达标检查时，请参考此指南。

## 1. 测试标准与覆盖率红线
目前平台已经集成了严密的覆盖率阈值监控，任何提交不得破坏以下标准线：
- **分支 (Branches)**: ≥ 70%
- **函数 (Functions)**: ≥ 70%
- **行 (Lines)**: ≥ 80%
- **语句 (Statements)**: ≥ 80%

*(参考文件: `web/vitest.config.ts`, 后端遵循同等严谨的 Pydantic 模型验证测试标准)*

## 2. 前端测试 (Vitest + MSW)
- **运行命令**：`cd web && npm run test:coverage`。
- **环境**：必须使用 `@testing-library/react` 与 `@testing-library/jest-dom`。
- **Mock 拦截**：一切不应该实际发起网络请求的测试组件，必须借助 MSW (Mock Service Worker) 实现 API 挂载拦截。切忌强耦合真实的后端网关状态。

## 3. 后端测试 (Pytest)
- **运行命令**：位于 `backend/tests/` 目录。
- **测试构成**：
  - `test_api_cases.py` / `test_api_logs.py` 等用于 RESTful API 的集成验证。
  - `test_integration.py` 负责核心的大跨度请求。
- **异步测试**：由于应用基于 FastAPI 和原生 Async/Await，测试固件里必须引用 `@pytest.mark.asyncio` 并使用 `AsyncClient` 模拟 HTTP 调用，防止 event loop 抢占冲突。

## 4. 自动化评测机制驱动 (Evaluation Driven)
在诊断代理发生逻辑改变后：
- 必须确保 `PYTHONPATH=./backend python3 backend/services/evaluation.py` 可以正常跑通现有内置的测试 Case 集合。
- 检查修改是否引发五维评分体系（命中率、ECU 精度等）的分数下滑。

## 5. Mock 数据管理
请定期验证 `backend/data/jira_mock/` 下的伪造 JSON 以及 `data/logs/` 的故障日志数据格式的一致性。测试数据在扩充时不得破坏旧有解析器的兼容逻辑。
