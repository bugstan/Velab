# Velab - FOTA 智能诊断平台

## 项目概览
基于 AI 的车辆固件升级 (FOTA) 诊断系统。采用多 Agent 协作架构，通过分析车辆日志、工单和技术文档，为技术人员提供智能化解决方案。

## 技术栈
- **后端 (Backend)**: Python 3.12, FastAPI (异步), Pydantic 2, OpenAI SDK, SSE-Starlette.
- **前端 (Frontend)**: Next.js 16 (App Router), React 19, Tailwind CSS 4, TypeScript 6.
- **测试**:
  - 后端 - Pytest
  - 前端 - Vitest 4.1.2, @vitest/coverage-v8, @vitest/ui
  - 测试库 - @testing-library/react 16.3.2, @testing-library/jest-dom 6.9.1
  - API Mock - MSW 2.12.14
  - Lint - ESLint 9

## 核心架构 & 文件夹说明
- `backend/`: FastAPI 后端核心。
  - `/agents/`: 所有的 Agent 逻辑。`base.py` 包含注册表。
    - `log_analytics.py` — 日志分析 Agent
    - `jira_knowledge.py` — Jira 工单检索 Agent
    - `doc_retrieval.py` — 技术文档检索 Agent (2026-04-06 新增)
    - `rca_synthesizer.py` — RCA 综合分析 Agent
    - `orchestrator.py` — 编排器
  - `/common/`: 全链路日志 (trace_id) 和脱敏 (redaction) 逻辑。
  - `/services/`: 核心服务层。
    - `llm.py` — 统一的 LLM 客户端抽象
    - `vector_search.py` — TF-IDF/向量检索服务 (2026-04-06 新增)
    - `semantic_cache.py` — 语义缓存服务 (2026-04-06 新增)
    - `tool_functions.py` — Agent Tool Use 函数 (2026-04-06 新增)
    - `doc_chunker.py` — PDF/文本切块服务 (2026-04-06 新增)
    - `evaluation.py` — 诊断评测框架 (2026-04-06 新增)
    - `workspace_manager.py` — Agent Markdown 工作区沙盒管理
    - `time_alignment.py` — 多域日志时间对齐服务
    - `event_normalizer.py` — 事件标准化服务
  - `/api/`: RESTful API 接口层（22 个端点）。
    - `feedback.py` — 诊断反馈 API (2026-04-06 新增)
    - `metrics.py` — Prometheus 监控指标 (2026-04-06 新增)
- `web/`: Next.js 前端应用。
  - `src/app/`: 页面和路由 (Page & API Routes).
  - `src/components/`: 高复用 React 组件（ChatMessage, ThinkingProcess）.
- `gateway/`: 基于 LiteLLM 的模型网关配置。

## 常用开发指令

### 后端
- **安装**: `pip install -r requirements.txt` (在 venv 中)
- **启动**: `python main.py` 或 `uvicorn main:app --reload`
- **测试**: `pytest`

### 前端
- **安装**: `npm install`
- **启动**: `npm run dev` (URL: http://localhost:3000)
- **测试**:
  - `npm test` - 运行所有测试
  - `npm run test:watch` - 监听模式
  - `npm run test:coverage` - 生成覆盖率报告
  - `npm run test:ui` - 可视化测试界面
- **检查**: `npm run lint`

## 编码与设计规范

### 1. 通用规则
- **Git 提交**: 遵循 Conventional Commits (例如: `feat:`, `fix:`, `docs:`)。
- **调用链追踪**: 所有后端方法应支持或生成 `trace_id` 用于全链路追踪。

### 2. 后端规范 (Python/FastAPI)
- **命名**: 使用 `snake_case`。所有异步方法名以 `async` 修饰。
- **Agent 注册**: 添加新 Agent 必须继承 `BaseAgent` 并在文件末尾手动调用 `registry.register()`。
- **敏感信息**: 严禁直接输出 VIN 码、手机号等。必须在 API 出口或日志记录处使用 `redactor` 装饰器或逻辑。

### 3. 前端规范 (TypeScript/React)
- **组件**: 使用函数式组件 (Functional Components)。
- **命名**: 组件名使用 `PascalCase`，变量和普通函数使用 `camelCase`。
- **样式**: 仅使用 Tailwind CSS 4 工具类，避免自定义纯 CSS。
- **类型**: 强制使用 TypeScript 类型，禁止无故使用 `any`。

## AI 记忆管理建议
- 本文件只维护**当前项目状态和规范**，不记录变更历史。保持精简以节省上下文窗口。
- 架构决策和变更记录请写入 `docs/DECISION_LOG.md`。
- 当开发流程规范发生变化时，直接更新本文件中对应的准则描述（反映最新状态，而非追加记录）。
