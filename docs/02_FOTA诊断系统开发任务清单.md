# FOTA诊断系统开发任务清单

## 1. 目标

基于 `demo.mp4` 反推的方案，落地一套可用的 **FOTA 故障诊断系统 MVP**。  
目标不是先做“聊天 UI”，而是先把以下核心能力串起来：

1. 多源日志可接入、可解析、可统一时间线。
2. 可检索历史 Jira / PDF / PPT / 技术文档。
3. 可通过编排层调度多个 Agent。
4. 可输出结构化的 RCA 结果与引用来源。

## 2. 建议阶段划分

### Phase 0：技术预研

目标：把风险点提前打掉。

### Phase 1：MVP 核心链路

目标：实现“提问 -> 日志分析 -> 文档/Jira检索 -> 报告输出”。

### Phase 2：工程化增强

目标：支持更大规模日志、更多车型、更多知识源、权限和审计。

---

## 3. 总体任务拆分

| 模块 | 负责人建议 | 优先级 | 目标 |
|------|------------|--------|------|
| 前端 | 前端工程师 | P1 | 聊天式诊断 UI + 来源展示 |
| 编排层 | 后端/AI工程师 | P0 | Orchestrator + Agent 调度 |
| 日志解析 | 后端/日志工程师 | P0 | 多源日志统一解析与时间线 |
| 知识库 | 后端/数据工程师 | P0 | Jira / PDF / PPT / 文档检索 |
| 报告生成 | AI工程师 | P0 | RCA、建议、引用、置信度 |
| 数据存储 | 后端工程师 | P0 | 元数据、向量、原始文件管理 |
| 评测与验收 | QA / 算法评测 | P1 | 正确率、稳定性、可追溯性 |
| 运维部署 | DevOps | P2 | 部署、监控、日志、权限 |

---

## 4. 前端开发任务

### 4.1 页面框架

#### 任务

1. 新建聊天式诊断页面。
2. 支持 Demo 模式切换。
3. 支持输入问题、查看结果、查看历史会话。

#### 交付物

1. `ChatPage`
2. `SessionHistoryPanel`
3. `DemoSwitcher`

#### 验收标准

1. 可以输入问题并提交。
2. 可以展示流式返回结果。
3. 可以切换不同分析模式。

### 4.2 Agent 执行状态面板

#### 任务

1. 展示 `Parallel Orchestrator` 执行步骤。
2. 展示每个 Agent 的运行中 / 完成 / 失败状态。
3. 支持折叠中间过程。

#### 交付物

1. `AgentTimeline`
2. `IntermediateStepsPanel`

#### 验收标准

1. 用户能看到每个 Agent 的执行顺序和状态。
2. 中间过程默认折叠，可展开。

### 4.3 报告展示组件

#### 任务

1. 结构化展示：
   - Summary
   - Root Cause
   - Recommendations
   - Confidence
   - Sources
2. 支持引用跳转到来源片段。
3. 支持导出 Markdown / PDF。

#### 交付物

1. `RcaReportView`
2. `EvidenceSourcePanel`
3. `ExportButton`

#### 验收标准

1. 报告内容可读、可复制。
2. 点击来源可定位到引用片段。

---

## 5. 编排层开发任务

### 5.1 Query Router

#### 任务

1. 根据用户问题识别分析类型：
   - 仅日志分析
   - 日志 + Jira
   - 日志 + 文档
   - 联合 RCA
2. 生成标准化任务对象。

#### 输入

1. 用户自然语言问题
2. 会话上下文
3. 可选日志文件 / 项目上下文

#### 输出

```json
{
  "intent": "fota_rca",
  "need_log_agent": true,
  "need_jira_agent": true,
  "need_doc_agent": true,
  "query_entities": ["iCGM", "MPU", "FOTA"]
}
```

#### 验收标准

1. 至少能正确区分 4 类问题。
2. 关键实体抽取正确率达到可用水平。

### 5.2 Parallel Orchestrator

#### 任务

1. 并行启动多个 Agent。
2. 管理超时、失败重试、结果汇总。
3. 为前端提供阶段性状态更新。

#### 交付物

1. `orchestrator.py`
2. `task_state_manager.py`

#### 验收标准

1. Log Agent 和 Jira Agent 能并行执行。
2. 某个 Agent 失败时不会拖垮整个请求。
3. 前端能实时拿到状态更新。

### 5.3 Agent 标准接口

#### 任务

定义统一 Agent 接口：

```python
class BaseAgent:
    def run(self, query, context) -> AgentResult:
        ...
```

#### 统一返回结构

```json
{
  "agent_name": "log_analytics",
  "status": "success",
  "summary": "...",
  "evidence": [],
  "structured_output": {}
}
```

#### 验收标准

1. 所有 Agent 输出统一格式。
2. Orchestrator 不关心 Agent 内部实现。

---

## 6. 日志解析开发任务

### 6.1 日志接入与分类

#### 任务

支持以下日志类型：

1. FOTA Java 日志
2. Android logcat
3. MCU 日志
4. iBDU 日志
5. TBox DLT 解析结果
6. HMI 日志

#### 交付物

1. `log_type_detector`
2. `source_registry`

#### 验收标准

1. 目录级扫描时能正确分类绝大多数日志文件。

### 6.2 统一日志模型

#### 任务

把不同格式的日志统一成事件模型。

#### 统一结构

```json
{
  "timestamp": "...",
  "source": "android",
  "module": "FotaDownloadImpl",
  "level": "ERROR",
  "message": "...",
  "raw": "...",
  "tags": ["fota", "download"]
}
```

#### 验收标准

1. 所有日志都能转成统一 JSON 事件。

### 6.3 时间线对齐

#### 任务

1. 支持 Android 绝对时间。
2. 支持 MCU 相对时间对齐。
3. 支持 iBDU 时间直接并入。
4. 支持 FOTA / TBox / Android 统一 timeline。

#### 交付物

1. `timeline_aligner.py`
2. `timestamp_normalizer.py`

#### 验收标准

1. 关键事件在统一时间线上误差控制在可接受范围。

### 6.4 FOTA 阶段识别

#### 任务

识别以下阶段：

1. 初始化
2. 版本检查
3. 下载
4. 解密 / 验签
5. 刷写
6. 重启
7. 升级结果

#### 交付物

1. `fota_stage_classifier.py`

#### 验收标准

1. 能自动输出一条 FOTA 状态机时间线。

### 6.5 异常锚点提取

#### 任务

识别关键异常：

1. 文件不存在
2. 校验失败
3. ECU 状态不一致
4. 升级状态重置
5. 网络中断
6. MCU / MPU Alive False
7. 重启 / reboot

#### 交付物

1. `error_anchor_extractor.py`

#### 验收标准

1. 对典型升级失败 case 能抽出关键异常链。

### 6.6 根因候选生成

#### 任务

基于规则和结构化结果，先产出候选根因，而不是直接交给 LLM 乱猜。

#### 示例输出

```json
[
  {
    "cause": "MPU大包下载被重启中断",
    "confidence": 0.87,
    "evidence_ids": ["e12", "e49", "e78"]
  }
]
```

#### 验收标准

1. 常见 FOTA 问题能得到稳定候选根因。

---

## 7. 知识库开发任务

### 7.1 Jira 同步

#### 任务

1. 通过 Jira API 拉取工单。
2. 提取标题、描述、根因、处理方案、版本信息。
3. 建立 issue 标签：
   - ECU
   - 平台
   - 车型
   - 模块
   - 错误类型

#### 交付物

1. `jira_sync_job.py`
2. `jira_issue_normalizer.py`

#### 验收标准

1. 可增量同步 Jira。
2. 能按关键词与语义检索到相似工单。

### 7.2 PDF / PPT / 文档解析

#### 任务

1. 解析 PDF
2. 提取 PPT 文本
3. 按标题/章节切块
4. 保留来源信息

#### 交付物

1. `doc_ingest_pipeline.py`
2. `chunker.py`

#### 验收标准

1. 可稳定提取文档正文。
2. 每个 chunk 都能回溯原文件和章节。

### 7.3 检索系统

#### 任务

实现混合检索：

1. 关键词检索
2. 向量检索
3. 重排序

#### 交付物

1. `retrieval_service.py`
2. `reranker.py`

#### 验收标准

1. 输入一个问题，能同时召回：
   - 历史 Jira
   - 离线技术文档
   - 相关日志结论

---

## 8. 报告生成开发任务

### 8.1 结果汇总器

#### 任务

将多个 Agent 输出合并成统一输入：

1. 日志结论
2. Jira 相似案例
3. 文档依据
4. 时间线证据

#### 交付物

1. `result_merger.py`

#### 验收标准

1. 可输出统一的 RCA 输入对象。

### 8.2 LLM 报告模板

#### 任务

生成固定结构报告：

1. Summary
2. Confidence Level
3. Technical Response
4. Recommendations
5. Sources

#### 交付物

1. `report_prompt.py`
2. `report_generator.py`

#### 验收标准

1. 报告结构稳定。
2. 每条核心结论都能回指来源。

### 8.3 置信度模型

#### 任务

不要让 LLM 直接随意写“高/中/低”，要基于证据强度计算。

#### 输入维度

1. 日志证据数量
2. 跨源一致性
3. 是否命中历史 Jira
4. 是否命中文档规则

#### 交付物

1. `confidence_scorer.py`

#### 验收标准

1. 置信度计算有稳定规则。

---

## 9. 数据存储与基础设施任务

### 9.1 原始文件存储

#### 任务

1. 存日志原文件
2. 存文档原文件
3. 存视频、报告等附件

#### 建议

1. 本地开发：文件系统
2. 生产环境：对象存储

### 9.2 元数据数据库

#### 任务

保存：

1. 会话记录
2. 文件索引
3. 解析结果元数据
4. Agent 执行记录

#### 建议

1. `PostgreSQL`

### 9.3 向量库

#### 任务

为 Jira / 文档 / 历史报告建 embedding 检索。

#### 建议

1. MVP：`pgvector`
2. 后续：`Milvus` 或 `OpenSearch Vector`

---

## 10. 评测与验收任务

### 10.1 基准测试集建设

#### 任务

构建一组标准 case：

1. iCGM 死循环下载
2. 文件校验失败
3. ECU 状态不一致
4. 网络中断导致升级失败
5. 重启中断下载

### 10.2 评测指标

#### 指标

1. 根因命中率
2. 证据引用正确率
3. 相似 Jira 召回率
4. 报告可读性
5. 响应时间

### 10.3 人工评审

#### 任务

由领域专家评审：

1. 结论是否靠谱
2. 证据是否站得住
3. 建议是否可执行

---

## 11. 运维与部署任务

### 11.1 部署方案

#### MVP

1. 前端：Nginx (Static Host)
2. 后端：FastAPI + Systemd (原生部署)
3. PostgreSQL + pgvector (原生部署)

### 11.2 监控

#### 任务

1. 请求耗时
2. Agent 成功率
3. 检索命中率
4. LLM 调用耗时和失败率

### 11.3 权限控制

#### 任务

1. 文档权限
2. Jira 权限
3. 操作审计

---

## 12. 建议排期

### Sprint 1

1. 日志统一解析
2. 时间线对齐
3. FOTA 阶段识别
4. 最基础的报告生成

### Sprint 2

1. Jira 同步与检索
2. PDF/PPT 文档入库
3. Orchestrator + 多 Agent

### Sprint 3

1. 前端聊天页
2. 执行步骤展示
3. 来源引用与导出

### Sprint 4

1. 评测集建设
2. 置信度模型
3. 工程化优化

---

## 13. MVP 最小闭环清单

如果只做最小闭环，必须完成的任务是：

1. 多源日志解析
2. 统一时间线
3. FOTA 异常锚点提取
4. 一个 Log Analytics Agent
5. 一个 Jira / Doc 检索 Agent
6. 一个 Orchestrator
7. 一个报告输出器
8. 一个最小聊天界面

## 14. 推荐优先级

### P0

1. 日志解析
2. 时间线合并
3. FOTA 阶段识别
4. 根因候选提取
5. 报告生成

### P1

1. Jira 检索
2. PDF/PPT 检索
3. 前端 UI
4. Agent 状态展示

### P2

1. 权限体系
2. 部署监控
3. 高级评测
4. 多车型多项目扩展

