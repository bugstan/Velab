# Velab 项目现状与进度分析文档

## 1. 项目定位
Velab（Vehicle Laboratory）是一个针对 **FOTA（Firmware Over-The-Air）故障诊断** 的 AI 原型验证项目。它旨在通过大模型（LLM）驱动的多智能体（Multi-Agent）协作，实现从原始日志到根因分析报告的自动化生成。

## 2. 现状分析（基于当前代码库）

### 2.1 核心架构
- **后端 (FastAPI)**: 采用了异步（AsyncIO）架构，支持 SSE（Server-Sent Events）流式输出，保证了诊断过程的实时可见性。
- **编排层 (Orchestrator)**: 采用 **MiniMax M2.5** 模型作为核心编排器，支持 Function Calling（工具调用）模式，能够根据用户问题自主决定调用哪些 Agent。
- **Agent 层**: 实现了 `Log Analytics`（日志分析）和 `Jira Knowledge`（工单知识库）两个核心 Agent，形成了「日志+案底」的闭环分析能力。

### 2.2 已完成功能 (P0/P1)
- [x] **SSE 流式响应**: 实现了类似 ChatGPT 的打字机输出效果，并包含思维链（Thinking）展示。
- [x] **智能路由**: Orchestrator 能够识别寒暄、引导用户补充信息（车型、ECU 等）以及分发诊断任务。
- [x] **工具化调用**: 诊断 Agent 均注册到统一的 `registry` 中，Orchestrator 通过动态工具定义进行调度。
- [x] **追踪与日志**: 包含 `chain_log` 机制，支持 `trace_id` 追踪，便于调试复杂的并行调用链路。
- [x] **兜底机制**: 当模型不可用时，具备生成基础结构化报告的 Fallback 逻辑。

### 2.3 待完善/进度空白 (Gap)
- [ ] **数据持久化**: 当前主要依赖内存和 Mock，缺乏成熟的数据库（如 PostgreSQL/pgvector）集成。
- [ ] **离线解析管线**: 虽然有日志分析 Agent，但缺乏将 1GB 级原始二进制日志解析为结构化事件的离线 ETL 管线。
- [ ] **RAG 向量搜索**: `jira_knowledge` Agent 目前多为 Mock 或简单关键字匹配，尚未接入真正的向量检索。
- [ ] **前端深度交互**: 当前前端主要负责聊天展示，缺乏对诊断结论中引用原始日志、时序图等细节的深度交互支持。

## 3. 进度总结

| 维度 | 进度 | 评价 |
|---|---|---|
| **架构设计** | 85% | 核心编排逻辑成熟，SSE 与 Trace 机制完善 |
| **核心算法/Prompt** | 70% | 编排 Prompt 已迭代多次，具备较好的意图识别能力 |
| **业务逻辑** | 50% | 覆盖了主要的 FOTA 诊断场景，但 ECU 专项分析尚不深入 |
| **工程化/部署** | 40% | 暂无完整的 Systemd 部署脚本，依赖手动配置 .env |

## 4. 下一步演进建议
1.  **接入 RAG 服务**: 在 `backend/services/` 下新增 `vector_search.py`，接入 pgvector 存储 Jira 历史故障。
2.  **强化日志 Agent**: 引入真实解析插件（如针对 Android Logcat、DLT 的解析器）。
3.  **完善文档系统**: 增加 `docs_agent`，使系统能根据 PDF/PPT 形式的技术规范进行推理。
4.  **去 Docker 化生产落地**: 编写对应的 Systemd 服务单元文件，实现无容器化的生产环境部署。