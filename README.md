# Velab - FOTA 智能诊断平台

**Velab (Vehicle Laboratory)** 是一个面向 **FOTA (Firmware Over-The-Air) 故障根因分析** 的多智能体（Multi-Agent）智能诊断平台。

该项目通过 LLM 驱动的 Orchestrator 协调多个专项 Agent（日志分析、Jira 检索、文档检索），实现从海量原始数据到结构化诊断结论的自动化流转，并支持 SSE 实时的思维链展示。

---

## 🎯 核心特性

- ✅ **多智能体协同诊断**: Log Analytics + Jira + Doc Retrieval 三路证据融合
- ✅ **纯 Python async 编排**: 高性能、易调试、完全可控
- ✅ **双供应商 Fallback**: Claude 主力 + OpenAI 备用，自动切换
- ✅ **时间窗口裁剪**: 快速通道 2~5 分钟完成诊断（vs 30 分钟全量解析）
- ✅ **语义缓存**: 预估 50~70% 缓存命中率，显著降低成本
- ✅ **防幻觉护栏**: 引用 ID 断言验证 + 置信度量化计算
- ✅ **可追溯证据链**: 每条结论都能回溯到原始日志行号
- ✅ **生产级部署**: systemd + Nginx + 完整运维文档

---

## 📁 项目结构

```
Velab/
├── backend/              # FastAPI 后端服务
│   ├── agents/           # Agent 实现（Log/Jira/Doc/RCA）
│   ├── api/              # 平台业务 API（cases/feedback/sessions）
│   ├── log_pipeline/     # 整车日志摄取管线（M1-M6，独立子系统）
│   ├── models/           # SQLAlchemy ORM 模型
│   ├── services/         # 核心服务（LLM/VectorSearch/WorkspaceManager 等）
│   ├── tasks/            # Arq 异步任务队列
│   ├── tests/            # API 单元测试和集成测试
│   └── README.md         # Backend 部署文档
│
├── gateway/              # LiteLLM API 中转层
│   └── ...
├── web/                  # Next.js 前端
│   ├── src/app/api/      # API 路由（chat/upload/bundle/sessions）
│   ├── src/components/   # React 组件（含 SessionSidebar/UploadSummaryCard）
│   └── ...
├── docs/                 # 项目文档
└── scripts/              # 统一脚本
    ├── dev.sh            # 一键启动（Backend + Frontend + 按需 Gateway）
    ├── test-ci.sh        # 本地 CI 验证（PR 前必跑）
    └── deploy-all.sh     # 单机一键部署
```

---

## 🚀 快速启动

### ⚡ 一键启动（推荐）

```bash
# 克隆并进入项目
git clone https://github.com/tomguo2000/Velab.git && cd Velab

# 配置后端环境变量
cp backend/.env.example backend/.env
# 编辑 backend/.env，设置 DEPLOYMENT_MODE（A 或 B）及对应的 API Key

# 一键启动（同时启动 Backend + Frontend，按需启动 Gateway）
bash scripts/dev.sh
```

脚本会自动：
- 停止占用 8000 / 3000 端口的旧进程
- 读取 `backend/.env` 中的 `DEPLOYMENT_MODE`：
  - **场景 A**（国内）：自动检测并启动 LiteLLM Gateway（4000 端口）
  - **场景 B**（海外）：跳过 Gateway，直连 Claude / OpenAI
- 按 `Ctrl+C` 同时停止所有子服务

> **场景 A 前置条件**：需先配置 `gateway/.env` 并安装 `litellm`（`pip install litellm`）

---

### 手动启动（分步）

#### 1. 启动 Gateway（场景 A：平台在国内）

```bash
cd gateway
cp .env.example .env
# 编辑 .env，填入真实的 API Keys
./scripts/start.sh
```

#### 2. 启动 Backend

```bash
cd backend
cp .env.example .env
# 编辑 .env，配置 DEPLOYMENT_MODE 和其他参数
./scripts/start-dev.sh
```

#### 3. 验证服务

```bash
# Backend 健康检查
curl http://localhost:8000/health

# Gateway 健康检查（如果启动了）
curl http://localhost:4000/health

# API 文档
open http://localhost:8000/docs
```

### 生产环境

详细部署步骤请参考：
- [Backend 部署文档](backend/README.md)
- [Gateway 部署文档](gateway/README.md)
- [生产部署指南](docs/生产部署指南_V1.md)

---

## 🏗️ 部署架构

### 场景 A：平台在国内（需要 Gateway 中转）

```
┌─────────────────────────────────────┐
│ 中国服务器                            │
│ ┌─────────┐  ┌──────────┐           │
│ │ Web前端  │  │ Backend  │           │
│ │ Nginx   │  │ FastAPI  │           │
│ └─────────┘  └──────────┘           │
│                    │                 │
│                    │ HTTPS (跨境)    │
└────────────────────┼─────────────────┘
                     │
                     ▼
┌─────────────────────────────────────┐
│ 美国 CN2 GIA 服务器                  │
│ ┌─────────────────────────────┐     │
│ │ Gateway (LiteLLM Proxy)     │     │
│ │ - Key Pool 轮转              │     │
│ │ - Fallback 机制              │     │
│ └─────────────────────────────┘     │
└─────────────────────────────────────┘
```

### 场景 B：生产在海外（直连 LLM API）

```
┌─────────────────────────────────────┐
│ 海外云服务器                          │
│ ┌─────────┐  ┌──────────┐           │
│ │ Web前端  │  │ Backend  │           │
│ │ Nginx   │  │ FastAPI  │           │
│ └─────────┘  └──────────┘           │
│                    │                 │
│                    │ 直连（无需中转）  │
└────────────────────┼─────────────────┘
                     │
                     ▼
              Claude/OpenAI API
```

---

## 📊 开发进度

| 模块 | 完成度 | 状态 |
|------|--------|------|
| 基础设施与部署 | 100% | ✅ 完成 |
| 离线预处理管线 | 100% | ✅ 完成 |
| 数据库与API | 100% | ✅ 完成 |
| 任务队列集成 | 100% | ✅ 完成 |
| API测试 | 100% | ✅ 完成 |
| MVP核心功能 | 100% | ✅ 完成 |
| 前端交互功能 | 100% | ✅ 完成 |
| 前端日志上传工作流 | 100% | ✅ 完成 |
| **log_pipeline M1-M6** | 100% | ✅ 完成（107 项测试）|
| **单元测试覆盖** | 100% | ✅ 后端 219 passed / 前端 201 passed |
| **安全加固** | 100% | ✅ 完成（0 CVE）|
| **开发工具链（CI/dev.sh）** | 100% | ✅ 完成 |
| 后端核心逻辑（在线诊断增强） | 100% | ✅ 完成 |
| 数据与演示场景 | 90% | ✅ 基本完成 |
| 评测与验收 | 70% | 🚧 剩余人工评审 |

**总体进度**: 约 **99%**（剩余：真实 Jira 数据同步、权限体系与操作审计、人工评审）

> 📊 测试覆盖率（2026-05-03）：后端 219 passed；前端 statements 84.7% / branches 74.4% / lines 87.8%，全部高于红线。

详细任务清单请查看：
- [TODO.md](docs/TODO.md) - 项目任务清单（最新）
- [MVP实施总结报告](docs/MVP实施总结报告.md) - MVP实施详细报告
- [P0任务实施进度报告](docs/P0任务实施进度报告.md) - P0离线预处理管线实施报告

---

## 📚 核心文档

### 快速入门

- **[CLAUDE.md](CLAUDE.md)** - 完整项目文档（开发指南、API 文档、部署指南）⭐ 推荐首先阅读
- **[TODO.md](docs/TODO.md)** - 项目任务清单（最新进度）
- **[Agent内存重构方案](docs/Agent内存_Markdown化重构方案.md)** - Sprint 5 核心架构设计文档 ⭐
- **[Workspace评测报告](docs/Workspace评测基准报告.md)** - 系统性能与诊断质量基准报告 ⭐

### 实施报告

- **[MVP实施总结报告](docs/MVP实施总结报告.md)** - MVP实施详细报告 ⭐ 最新完成
- [P0任务实施进度报告](docs/P0任务实施进度报告.md) - P0离线预处理管线实施报告
### 系统设计

- [AI专家项目分析报告](docs/AI专家项目分析报告.md) - 项目深度分析（⭐⭐⭐⭐⭐ 4.8/5.0）
- [技术设计方案（修订版 v6）](docs/FOTA智能诊断平台_可行性方案（修订版v6）.md) - 系统架构设计（最终执行版）
- [FOTA智能诊断平台_可行性方案（修订版v6）](docs/FOTA智能诊断平台_可行性方案（修订版v6）.md) - 可行性分析

### 部署运维

- [Backend README](backend/README.md) - Backend 部署文档
- [Gateway README](gateway/README.md) - Gateway 部署文档
- [Web README](web/README.md) - 前端部署文档
- [生产部署指南](docs/生产部署指南_V1.md) - 生产环境完整部署指南

### 技术方案

- [FOTA_LLM_API中转方案](docs/FOTA_LLM_API中转方案.md) - LLM API 中转架构
- [LLM_429限流防御方案](docs/LLM_429限流防御方案.md) - 限流防御策略（五层防御）

---

## 🛠️ 技术栈

| 层次 | 技术 |
|------|------|
| 后端框架 | Python 3.12 + FastAPI |
| AI 编排 | 纯 Python async + LangChain Tool 抽象 |
| LLM 供应商 | Claude（主力）+ OpenAI（Fallback + Embedding） |
| 任务队列 | Arq（原生 async/await） |
| 数据库 | PostgreSQL + pgvector |
| 对象存储 | MinIO / S3 |
| 缓存 | Redis |
| 前端框架 | Next.js 16 + React 19 + TypeScript 6 |
| 前端样式 | Tailwind CSS 4 |
| 前端测试 | Vitest 4.1 + React Testing Library 16.3 + MSW 2.12 |
| 服务部署 | Python Virtualenv + Systemd（反 Docker） |

---

## 🔐 安全注意事项

- ⚠️ **请勿提交任何包含真实 API Key 的 `.env` 文件**
- ⚠️ `.env` 文件权限应设置为 `600`
- ⚠️ 生产环境必须使用 HTTPS（Let's Encrypt 或 Cloudflare SSL）
- ⚠️ 定期轮换 API Keys
- ⚠️ 原始日志数据需脱敏处理后再送 LLM

---

##  开发原则

- ✅ **反 Docker**：生产部署使用 Systemd 管理 Python 虚拟环境
- ✅ **务实选型**：优先选择成熟稳定的技术栈
- ✅ **可追溯性**：每个结论都能回溯到原始数据
- ✅ **防幻觉**：引用 ID 断言验证 + 置信度量化计算
- ✅ **可观测性**：从 Day 1 起内建结构化日志和监控

---

**项目状态**: 🚧 开发中（Sprint 5 已完成，进入 Sprint 6 LLM 接入与生产部署阶段）
**最后更新**: 2026-05-03
