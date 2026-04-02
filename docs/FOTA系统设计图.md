# FOTA 多域日志智能诊断系统 — 设计图文档

> 本文档提取自《FOTA智能诊断平台_系统设计方案.md》v4，专门汇集系统各层架构图、流程图、时序图，供开发、评审和演示使用。

---

## 图 1：系统总体分层架构

```mermaid
flowchart TB
    UI["🖥️ 表现交互层\nWeb工作台 / 车端诊断看板"]
    GW["🌐 网关层\nFastAPI 网关服务 · HTTP / WebSocket"]
    ORC["🧠 Orchestrator\n意图解析"]
    QR["🔀 Query Router\n条件路由 · 按需启动"]
    LA["📋 Log Analytics Agent\n日志侦探"]
    JA["🗂️ Maxus Jira Agent\n历史档案专家"]
    DA["📄 Doc Retrieval Agent\n技术规范专家"]
    SYN["⚖️ RCA Synthesizer\n证据汇总 · 报告生成"]
    PG[("🗄️ PostgreSQL\n结构化时间轴事件")]
    VEC[("🔍 pgvector\njira_embeddings / doc_embeddings")]
    MINIO[("📦 MinIO\n原始日志归档")]

    UI -->|HTTP/WebSocket 请求| GW
    GW -->|任务投递| ORC
    ORC --> QR
    QR -.Send 并行.-> LA
    QR -.Send 并行.-> JA
    QR -.Send 并行.-> DA
    LA ==log_evidence · Reducer==> SYN
    JA ==jira_references · Reducer==> SYN
    DA ==doc_rules · Reducer==> SYN
    SYN -->|流式 JSON 报告| GW
    GW -->|渲染结论| UI
    LA --> PG
    LA --> MINIO
    JA --> VEC
    DA --> VEC
```

---

## 图 2：离线数据预处理管线

```mermaid
flowchart TD
    subgraph 日志预处理链路
        A1[日志包上传
zip/tar.gz/单文件] --> B1[Case Intake Service
创建案件·识别VIN/版本/时间范围]
        B1 --> C1[(MinIO
原始文件归档)]
        B1 --> D1[File Staging Service
解压·MIME识别·来源预分类]
        D1 --> E1[Parser Service
7类格式插件并行解析]
        E1 -->|解析失败| ERR1[案件标记 PARSE_FAILED
发告警·停止后续]
        E1 --> F1[Time Alignment Service
多域时钟偏移校准·生成 normalized_ts]
        F1 -->|全域对齐失败| ERR2[案件标记 ALIGN_FAILED
降级继续分析·报告顶部加警告横幅·异步告警通知]
        F1 -->|部分域对齐失败| WARN1[案件标记 ALIGN_PARTIAL
继续分析·时序结论加警告标签]
        WARN1 --> G1
        F1 -->|对齐成功| G1[Event Normalizer
语义归一化·降噪·事件分类]
        G1 -->|归一化失败| ERR3[案件标记 NORMALIZE_FAILED
发告警·停止后续]
        G1 --> H1[(PostgreSQL
标准事件表·统一时间轴)]
    end

    subgraph Jira知识库链路
        A2[Jira 工单同步] --> B2[Issue 清洗·摘要抽取]
        B2 --> C2[Embedding 向量化]
        C2 --> D2[(pgvector
jira_embeddings 表
HNSW 索引)]
    end

    subgraph 文档知识库链路
        A3[PDF/PPT/技术文档同步] --> B3[OCR·文本切块·章节保留]
        B3 --> C3[Embedding 向量化]
        C3 --> D3[(pgvector
doc_embeddings 表
HNSW 索引)]
    end
```

---

## 图 3：在线诊断请求完整时序

```mermaid
sequenceDiagram
    participant U as 工程师
    participant UI as Web工作台
    participant GW as FastAPI网关
    participant MQ as Redis/RabbitMQ
    participant ORC as Orchestrator
    participant QR as Query Router
    participant LA as Log Agent
    participant JA as Jira Agent
    participant DA as Doc Agent
    participant SYN as Synthesizer
    participant VER as 断言验证器

    U->>UI: 输入问题（如 iCGM 为何挂死）
    UI->>GW: POST /diagnose
    GW->>MQ: 入队（削峰）
    MQ->>ORC: Worker 消费任务
    ORC->>QR: 解析意图·生成 active_agents
    par 真正并行
        QR-->>LA: Send(state)
        QR-->>JA: Send(state)
        QR-->>DA: Send(state)
    end
    LA-->>SYN: log_evidence（Reducer 追加）
    JA-->>SYN: jira_references（Reducer 追加）
    DA-->>SYN: doc_rules（Reducer 追加）
    SYN->>VER: 输出报告草稿
    VER->>VER: 校验引用 ID 真实性
    alt 引用全部有效
        VER-->>GW: 高置信度报告
    else 存在虚假引用
        VER-->>GW: 标记[低置信度/需人工复核]
    end
    GW-->>UI: 流式推送 JSON 报告
    UI-->>U: 渲染诊断结论·证据来源·建议
```

---

## 图 4：LangGraph 状态图（State Machine）

```mermaid
stateDiagram-v2
    [*] --> query_router: START
    query_router --> Agent_Log: active_agents 含 log
    query_router --> Agent_Jira: active_agents 含 jira
    query_router --> Agent_Doc: active_agents 含 doc
    Agent_Log --> Synthesizer: log_evidence 写回 State
    Agent_Jira --> Synthesizer: jira_references 写回 State
    Agent_Doc --> Synthesizer: doc_rules 写回 State
    Synthesizer --> [*]: END

    note right of query_router
        Literal 约束：active_agents
        只能包含 log / jira / doc
    end note

    note right of Synthesizer
        三路并行分支全部完成后触发
        add_edge([Agent_Log,Agent_Jira,Agent_Doc], Synthesizer)
        显式声明 fan-in，保证框架版本兼容
    end note
```

---

## 图 5：多 Agent 工具调用关系图

```mermaid
flowchart LR
    subgraph Log Analytics Agent
        LA_T1[extract_timeline_events
case_id / module / time_range]
        LA_T2[fetch_raw_line_context
file_id / line_number / context_lines]
        LA_T3[search_fota_stage_transitions
case_id]
    end

    subgraph Jira Agent
        JA_T1[vector_search_jira_issues
query_embedding / top_k / filters]
        JA_T2[get_jira_issue_detail
issue_id]
    end

    subgraph Doc Retrieval Agent
        DA_T1[search_document_knowledge_base
query / doc_type / top_k]
        DA_T2[get_document_chunk
chunk_id]
    end

    LA_T1 --> PG[(PostgreSQL
标准事件表)]
    LA_T2 & LA_T3 --> MINIO[(MinIO
原始日志)]
    JA_T1 & JA_T2 --> VEC1[(pgvector
jira_embeddings)]
    DA_T1 & DA_T2 --> VEC2[(pgvector
doc_embeddings)]
```

---

## 图 6：置信度计算流程

```mermaid
flowchart LR
    A[断言验证器
校验引用 ID] -->|citation_valid_rate| CALC
    B[Jira 检索
最高相似度得分] -->|jira_top_similarity| CALC
    C[日志命中条数
min 条数/5, 1.0] -->|log_evidence_count_score| CALC
    D[时间对齐服务
对齐可信度均值] -->|time_align_confidence| CALC

    CALC[加权求和
0.4·A + 0.2·B + 0.2·C + 0.2·D]

    CALC -->|>= 0.6| HIGH[高置信度报告
直接输出]
    CALC -->|< 0.6| LOW[低置信度报告
标记需人工复核]
```

---

## 图 7：时间对齐降级策略流程

```mermaid
flowchart TD
    START[Time Alignment Service
执行多域时钟对齐]
    START --> CHECK{检查各域
clock_confidence}

    CHECK -->|所有域 >= 0.8| OK[对齐成功
正常进入 Agent 分析]
    CHECK -->|部分域 < 0.8| PARTIAL[案件标记 ALIGN_PARTIAL
继续分析
涉及该域时序结论加警告标签]
    CHECK -->|无法找到跨域锚点| FAIL[案件标记 ALIGN_FAILED
降级继续分析
使用各域原始时间戳]

    OK --> AGENT[进入在线诊断 Agent 编排]
    PARTIAL --> AGENT
    FAIL --> WARN_BANNER[报告顶部加⚠️警告横幅
时序结论不可信·仅供参考]
    WARN_BANNER --> AGENT
    FAIL --> ALERT[异步告警通知
邮件/Webhook 提示补充日志]
```

---

## 图 8：并发控制与防串线架构

```mermaid
flowchart TD
    subgraph 接入层
        REQ[多用户并发请求]
        GW[FastAPI 网关]
    end

    subgraph 削峰层
        MQ[Redis / RabbitMQ 消息总线]
        POD1[K8s Worker Pod 1]
        POD2[K8s Worker Pod 2]
        PODN[K8s Worker Pod N]
    end

    subgraph 隔离层
        T1[thread_id 沙盒 1
AsyncPostgresSaver Checkpoint]
        T2[thread_id 沙盒 2
AsyncPostgresSaver Checkpoint]
        TN[thread_id 沙盒 N
AsyncPostgresSaver Checkpoint]
    end

    subgraph 限流层
        RL[令牌桶 + 指数退避重试
防止 429 Too Many Requests]
        LLM[LLM API
Gemini / Claude]
    end

    REQ --> GW --> MQ
    MQ --> POD1 & POD2 & PODN
    POD1 --> T1
    POD2 --> T2
    PODN --> TN
    T1 & T2 & TN --> RL --> LLM
```
