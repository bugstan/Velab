# Velab 项目任务清单

> **最后更新**: 2026-04-04
> **当前阶段**: Sprint 2 - P0核心功能已完成，P1在线诊断进行中
> **下一阶段**: Sprint 3 - 前端UI开发

---

## ✅ 已完成任务

### 1. 基础设施与部署配置 (P0) - 100% 完成

- [x] **Backend 部署配置完整**
  - [x] 创建 `backend/scripts/deploy.sh` - 生产环境自动化部署
  - [x] 创建 `backend/scripts/start-dev.sh` - 开发环境启动
  - [x] 创建 `backend/systemd/fota-backend.service` - systemd 服务
  - [x] 创建 `backend/nginx/backend.conf` - Nginx 反向代理
  - [x] 完善 `backend/.env.example` - 环境变量配置
  - [x] 创建 `backend/README.md` - 完整部署文档

- [x] **Gateway 部署配置完整**
  - [x] 补充 `gateway/config.yaml` - Key Pool 配置
  - [x] 创建 `gateway/scripts/deploy.sh` - 生产环境自动化部署
  - [x] 创建 `gateway/scripts/start.sh` - 开发环境启动
  - [x] 创建 `gateway/systemd/litellm.service` - systemd 服务
  - [x] 创建 `gateway/nginx/litellm.conf` - Nginx 反向代理（含 Cloudflare SSL）
  - [x] 完善 `gateway/.env.example` - 环境变量配置（含多 Key Pool）
  - [x] 完善 `gateway/README.md` - 完整部署文档

- [x] **统一部署脚本**
  - [x] 创建 `scripts/deploy-all.sh` - 单机开发环境一键部署

- [x] **项目文档**
  - [x] 创建 `docs/AI专家项目分析报告.md` - 项目深度分析
  - [x] 创建 `docs/部署配置完整性检查报告.md` - 配置完整性检查
  - [x] 创建 `gateway/gateway功能检查报告.md` - Gateway 功能检查

- [x] **代码注释完善 (2026-04-02 新增)**
  - [x] 后端 Python 文件头部注释和方法注释
    - [x] `backend/config.py` - 配置管理模块注释
    - [x] `backend/agents/base.py` - Agent 基类架构注释
    - [x] `backend/main.py` - FastAPI 服务入口注释
  - [x] 前端 TypeScript 文件头部注释和方法注释
    - [x] `web/src/app/api/chat/route.ts` - API 路由代理层注释
    - [x] `web/src/app/page.tsx` - 主页面组件注释
    - [x] `web/src/components/ChatMessage.tsx` - 消息组件注释
  - [x] 创建完整项目文档 `claude.md`
  - [x] 更新主 README 和各组件 README
  - [x] 更新 .gitignore（添加 Log/ 和 AI 文档忽略）
  - [x] 删除冲突的旧版 `scripts/deploy.sh`
  - [x] 全面代码审核（语法、类型、逻辑检查）
  - [x] 脚本环境检查和提示完善性审核

- [x] **前端测试框架完善 (2026-04-03 新增)**
  - [x] 配置 Vitest 4.1.2 测试框架
  - [x] 配置 React Testing Library 16.3.2
  - [x] 配置 MSW 2.12.14 用于 API 模拟
  - [x] 添加所有组件测试（ChatMessage, ThinkingProcess, InputBar, Header, WelcomePage, FeedbackButtons）
  - [x] 添加集成测试（page.tsx）
  - [x] 添加 API 路由测试（/api/chat）
  - [x] 配置测试覆盖率目标（分支≥70%, 函数≥70%, 行≥80%, 语句≥80%）
  - [x] 创建完整测试文档 `web/README_TESTING.md`
  - [x] 更新文档以反映测试框架变更

- [x] **离线数据预处理管线 (P0) - 100% 完成 (2026-04-04 新增)**
  - [x] **数据库 Schema 创建**
    - [x] `diagnosis_cases` 表（案件记录）
    - [x] `raw_log_files` 表（原始日志文件元数据）
    - [x] `diagnosis_events` 表（诊断事件详情）
    - [x] `confirmed_diagnosis` 表（已确认诊断缓存）
  - [x] **Parser Service 实现（7个解析器）**
    - [x] `parser_android` - Android logcat 解析
    - [x] `parser_fota` - FOTA 文本日志解析
    - [x] `parser_kernel` - kernel / tombstone / ANR 解析
    - [x] `parser_mcu` - MCU 日志解析
    - [x] `parser_dlt` - AUTOSAR DLT 格式解析
    - [x] `parser_ibdu` - iBDU 电源管理日志解析
    - [x] `parser_vehicle_signal` - 车辆信号导出文件解析
  - [x] **Time Alignment Service 实现**
    - [x] 锚点事件识别（Android启动/关键系统事件）
    - [x] 时钟偏移计算（线性回归拟合）
    - [x] `normalized_ts` 生成
    - [x] 三级降级策略（高/中/低置信度）
  - [x] **Event Normalizer 实现**
    - [x] 语义归一化（统一事件描述）
    - [x] 降噪（过滤冗余事件）
    - [x] 事件分类（ERROR/WARNING/INFO等）
  - [x] **数据库集成层**
    - [x] SQLAlchemy 2.0+ ORM模型
    - [x] 同步/异步数据库连接管理
    - [x] 批量操作优化（bulk_insert/upsert）
  - [x] **API接口层（15个端点）**
    - [x] Cases API（4个端点）- 案件管理（创建/查询/列表/删除）
    - [x] Logs API（4个端点）- 日志文件管理（上传/查询/列表/删除）
    - [x] Parse API（3个端点）- 解析任务提交/查询/时间对齐
    - [x] Events API（4个端点）- 事件查询/单个/摘要/导出
  - [x] **任务队列集成**
    - [x] Arq异步任务队列（基于Redis）
    - [x] Worker实现（parse_logs_task）
    - [x] 任务客户端（提交/查询/取消）
  - [x] **API测试（34个测试）**
    - [x] Cases API单元测试（9个测试）
    - [x] Parse API单元测试（8个测试）
    - [x] Events API单元测试（13个测试）
    - [x] 集成测试（4个测试）
  - [x] 创建完整实施报告 `docs/P0任务实施进度报告.md`

---

## 🚧 进行中任务

### 2. 后端核心逻辑实现 (P1) - 30% 完成

- [x] **基础框架搭建**
  - [x] FastAPI 应用入口 (`main.py`)
  - [x] Agent 注册机制 (`agents/base.py`)
  - [x] Orchestrator 编排器 (`agents/orchestrator.py`)
  - [x] LLM 服务抽象层 (`services/llm.py`)
  - [x] 结构化日志 (`common/chain_log.py`)

- [ ] **Log Analytics Agent 完整实现**
  - [ ] 实现时间窗口裁剪逻辑（根据故障时间点裁剪 ±15 分钟）
  - [ ] 接入真实 LLM 推理（替换 Mock 实现）
  - [ ] 实现 Tool Use：`extract_timeline_events`
  - [ ] 实现 Tool Use：`fetch_raw_line_context`
  - [ ] 实现 Tool Use：`search_fota_stage_transitions`

- [ ] **Jira Knowledge Agent RAG 化**
  - [ ] 创建 `services/vector_search.py` - 向量检索服务
  - [ ] 实现 Tool Use：`vector_search_jira_issues`
  - [ ] 实现 Tool Use：`get_jira_issue_detail`
  - [ ] 补充 FOTA 典型故障案例数据

- [ ] **Doc Retrieval Agent 实现**
  - [ ] 实现 Tool Use：`search_document_knowledge_base`
  - [ ] 实现 Tool Use：`get_document_chunk`

- [ ] **RCA Synthesizer 实现**
  - [ ] 多路证据汇总逻辑
  - [ ] 置信度量化计算
  - [ ] 引用 ID 断言验证

---

## 📋 待开始任务

### 3. 前端交互功能开发 (P1) - 0% 完成

- [ ] **SSE 流式渲染优化**
  - [ ] `<<<THINKING>>>` 标记内容灰色折叠框展示
  - [ ] Markdown 格式诊断报告渲染（表格 + 置信度标签）

- [ ] **引用来源面板**
  - [ ] 点击引用来源弹出浮窗
  - [ ] 展示对应的日志片段或 Jira 描述

- [ ] **执行状态 Timeline**
  - [ ] 展示 Orchestrator 调度各 Agent 的动态过程
  - [ ] Agent 状态实时更新（Analyzing... → Done）

- [ ] **聊天式诊断页面**
  - [ ] 问题输入框
  - [ ] 历史会话列表
  - [ ] Demo 模式切换

### 4. 数据与演示场景准备 (P2) - 0% 完成

- [ ] **演示日志集**
  - [ ] 在 `data/logs/` 放置 3-5 个典型 FOTA 故障日志样本
  - [ ] iCGM 死循环下载
  - [ ] 文件校验失败
  - [ ] ECU 状态不一致
  - [ ] 网络中断导致升级失败
  - [ ] 重启中断下载

- [ ] **场景引导词**
  - [ ] 预设 3 个引导提问
  - [ ] 「分析为何 iCGM 在 11:24 发生心跳丢失」
  - [ ] 「查询类似 FOTA-9123 的历史案例」
  - [ ] 「FOTA 升级失败的根本原因是什么」

- [ ] **Jira 工单数据**
  - [ ] 同步历史 Jira 工单
  - [ ] 向量化入库

- [ ] **技术文档数据**
  - [ ] PDF/PPT 文档切块
  - [ ] 向量化入库

### 5. 评测与验收 (P2) - 0% 完成

- [ ] **基准测试集建设**
  - [ ] 构建 5-10 个标准 case
  - [ ] 人工标注正确答案

- [ ] **评测指标**
  - [ ] 根因命中率
  - [ ] 证据引用正确率
  - [ ] 相似 Jira 召回率
  - [ ] 报告可读性
  - [ ] 响应时间

- [ ] **人工评审**
  - [ ] 领域专家评审结论是否靠谱
  - [ ] 证据是否站得住
  - [ ] 建议是否可执行

---

## 🎯 Sprint 规划

### Sprint 1（已完成）✅
- ✅ 基础架构搭建
- ✅ 部署配置完整
- ✅ 文档完善

### Sprint 2（进行中）🚧
- ✅ 离线预处理管线（Parser + Time Alignment + Event Normalizer）- 已完成
- ✅ 数据库集成层（ORM + 批量操作）- 已完成
- ✅ API接口层（15个端点）- 已完成
- ✅ 任务队列集成（Arq + Redis）- 已完成
- ✅ API测试（34个测试）- 已完成
- 🚧 三个 Agent 完整实现（Log + Jira + Doc）
- 🚧 RCA Synthesizer 实现
- 🚧 语义缓存实现

### Sprint 3（计划中）📅
- 📅 前端 UI 开发
- 📅 Agent 执行状态面板
- 📅 RCA 报告展示 + 引用来源跳转
- 📅 已确认诊断缓存 + 反馈闭环

### Sprint 4（计划中）📅
- 📅 评测集建设
- 📅 置信度模型校准
- 📅 权限体系与操作审计
- 📅 监控告警 Dashboard

---

## 📊 进度总览

| 模块 | 完成度 | 状态 |
|------|--------|------|
| 基础设施与部署 | 100% | ✅ 完成 |
| 代码注释与文档 | 100% | ✅ 完成 |
| 离线预处理管线 | 100% | ✅ 完成 |
| 数据库与API | 100% | ✅ 完成 |
| 任务队列集成 | 100% | ✅ 完成 |
| API测试 | 100% | ✅ 完成 |
| 后端核心逻辑（在线诊断） | 30% | 🚧 进行中 |
| 前端交互功能 | 0% | 📅 待开始 |
| 数据与演示场景 | 0% | 📅 待开始 |
| 评测与验收 | 0% | 📅 待开始 |

**总体进度**: 约 **60%**

---

## 🔗 相关文档

- **[claude.md](../claude.md)** - 完整项目文档（开发指南、API 文档、部署指南）⭐ 推荐首先阅读
- [AI专家项目分析报告](./AI专家项目分析报告.md) - 项目深度分析
- [部署配置完整性检查报告](./部署配置完整性检查报告.md) - 配置完整性检查
- [FOTA智能诊断平台_系统设计方案](./FOTA智能诊断平台_系统设计方案.md) - 系统架构设计
- [FOTA智能诊断平台_可行性方案（修订版v6）](./FOTA智能诊断平台_可行性方案（修订版v6）.md) - 可行性分析
- [Backend README](../backend/README.md) - Backend 部署文档
- [Gateway README](../gateway/README.md) - Gateway 部署文档
- [Web README](../web/README.md) - 前端部署文档

---

**最后更新**: 2026-04-04
**维护人**: AI 开发专家
