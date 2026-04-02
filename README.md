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
│   ├── agents/           # Agent 实现（Log/Jira/Doc）
│   ├── services/         # LLM 服务抽象层
│   ├── scripts/          # 部署和启动脚本
│   ├── systemd/          # systemd 服务配置
│   ├── nginx/            # Nginx 反向代理配置
│   └── README.md         # Backend 部署文档
│
├── gateway/              # LiteLLM API 中转层
│   ├── scripts/          # 部署和启动脚本
│   ├── systemd/          # systemd 服务配置
│   ├── nginx/            # Nginx 反向代理配置
│   ├── config.yaml       # LiteLLM 模型路由配置
│   └── README.md         # Gateway 部署文档
│
├── web/                  # Next.js 前端（未来）
│
├── docs/                 # 项目文档
│   ├── AI专家项目分析报告.md
│   ├── 部署配置完整性检查报告.md
│   ├── FOTA智能诊断平台_系统设计方案.md
│   ├── FOTA智能诊断平台_可行性方案（修订版v6）.md
│   ├── FOTA_LLM_API中转方案.md
│   ├── LLM_429限流防御方案.md
│   └── TODO.md           # 任务清单
│
└── scripts/              # 统一部署脚本
    └── deploy-all.sh     # 单机开发环境一键部署
```

---

## 🚀 快速启动

### 开发环境

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
- [部署配置完整性检查报告](docs/部署配置完整性检查报告.md)

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
| 后端核心逻辑 | 30% | 🚧 进行中 |
| 离线预处理管线 | 0% | 📅 待开始 |
| 前端交互功能 | 0% | 📅 待开始 |
| 数据与演示场景 | 0% | 📅 待开始 |
| 评测与验收 | 0% | 📅 待开始 |

**总体进度**: 约 **25%**

详细任务清单请查看：[TODO.md](docs/TODO.md)

---

## 📚 核心文档

### 快速入门

- **[claude.md](claude.md)** - 完整项目文档（开发指南、API 文档、部署指南）⭐ 推荐首先阅读

### 系统设计

- [AI专家项目分析报告](docs/AI专家项目分析报告.md) - 项目深度分析（⭐⭐⭐⭐⭐ 4.8/5.0）
- [FOTA智能诊断平台_系统设计方案](docs/FOTA智能诊断平台_系统设计方案.md) - 系统架构设计
- [FOTA智能诊断平台_可行性方案（修订版v6）](docs/FOTA智能诊断平台_可行性方案（修订版v6）.md) - 可行性分析

### 部署运维

- [Backend README](backend/README.md) - Backend 部署文档
- [Gateway README](gateway/README.md) - Gateway 部署文档
- [部署配置完整性检查报告](docs/部署配置完整性检查报告.md) - 配置完整性检查

### 技术方案

- [FOTA_LLM_API中转方案](docs/FOTA_LLM_API中转方案.md) - LLM API 中转架构
- [LLM_429限流防御方案](docs/LLM_429限流防御方案.md) - 限流防御策略（五层防御）

---

## 🛠️ 技术栈

| 层次 | 技术 |
|------|------|
| 后端框架 | Python + FastAPI |
| AI 编排 | 纯 Python async + LangChain Tool 抽象 |
| LLM 供应商 | Claude（主力）+ OpenAI（Fallback + Embedding） |
| 任务队列 | Arq（原生 async/await） |
| 数据库 | PostgreSQL + pgvector |
| 对象存储 | MinIO / S3 |
| 缓存 | Redis |
| 前端 | Next.js + React + TypeScript |
| 服务部署 | Python Virtualenv + Systemd（反 Docker） |

---

## 🔐 安全注意事项

- ⚠️ **请勿提交任何包含真实 API Key 的 `.env` 文件**
- ⚠️ `.env` 文件权限应设置为 `600`
- ⚠️ 生产环境必须使用 HTTPS（Let's Encrypt 或 Cloudflare SSL）
- ⚠️ 定期轮换 API Keys
- ⚠️ 原始日志数据需脱敏处理后再送 LLM

---

## 📞 技术支持

如有问题，请查看：
1. 各组件的 README 文档
2. [docs](docs/) 目录下的详细设计文档
3. [部署配置完整性检查报告](docs/部署配置完整性检查报告.md)

---

## 📝 开发原则

- ✅ **反 Docker**：生产部署使用 Systemd 管理 Python 虚拟环境
- ✅ **务实选型**：优先选择成熟稳定的技术栈
- ✅ **可追溯性**：每个结论都能回溯到原始数据
- ✅ **防幻觉**：引用 ID 断言验证 + 置信度量化计算
- ✅ **可观测性**：从 Day 1 起内建结构化日志和监控

---

**项目状态**: 🚧 开发中（Sprint 1 已完成，Sprint 2 进行中）  
**最后更新**: 2026-04-02  
**维护团队**: AI 开发专家
