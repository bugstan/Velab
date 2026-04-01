# Velab (AI_Veh)

**Velab (Vehicle Laboratory)** 是一个面向 **FOTA (Firmware Over-The-Air) 故障根因分析** 的多智能体（Multi-Agent）智能诊断平台原型。

该项目通过 LLM 驱动的 Orchestrator 协调多个专项 Agent（日志分析、工单检索等），实现从海量原始数据到结构化诊断结论的自动化流转，并支持 SSE 实时的思维链展示。

## 核心特性
- **多智能体编排 (Multi-Agent Orchestration)**: 基于 MiniMax / Claude 模型的自主意图识别与任务分发。
- **SSE 流式交互**: 实时展示 Agent 的推理过程（Thinking Process）与最终诊断报告。
- **高可用网关 (LLM Gateway)**: 内置 LiteLLM 中转层，支持多模型自动 Fallback 与请求重试。
- **可扩展 Agent 架构**: 采用插件式注册机制，易于新增 ECU 专项分析或 RAG 知识库 Agent。

## 项目结构
- `backend/` — 基于 FastAPI 的异步后端，负责 Agent 编排与模型接入。
- `web/` — 基于 Next.js 的现代 Web 交互前端。
- `gateway/` — 基于 LiteLLM 的 LLM API 中转层配置。
- `docs/` — 项目现状分析、TODO 清单及技术方案文档。
- `data/` — 日志样本与 Mock 数据存放目录（需根据 `.gitignore` 自行创建）。

## 快速启动

### 1. 启动 LLM 网关 (可选但推荐)
```bash
cd gateway
pip install 'litellm[proxy]'
# 配置 .env 后启动
litellm --config config.yaml --port 4000
```

### 2. 启动后端 API
```bash
cd backend
pip install -r requirements.txt
# 根据 .env.example 创建 .env 并填入 API Key
python main.py
```

### 3. 启动前端 UI
```bash
cd web
npm install
npm run dev
```

## 开发进度与计划
详见 [`docs/velab_analysis.md`](docs/velab_analysis.md) 与 [`docs/TODO.md`](docs/TODO.md)。

## 注意事项
- 请勿提交任何包含真实 API Key 的 `.env` 文件。
- 生产部署建议使用 `Systemd` 管理 Python 虚拟环境下的进程，**本项目强制不使用 Docker**。
