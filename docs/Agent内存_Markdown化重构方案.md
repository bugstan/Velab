# Velab FOTA 智能诊断平台 —— Agent 内存架构重构方案

> **文档版本**: v2.2
> **最后更新**: 2026-04-06
> **背景来源**: 基于行业前沿 Agent 设计模式（《击败5000万美元向量数据库的Markdown文件》），结合 Velab 现有代码库（`orchestrator.py`、`base.py`、`rca_synthesizer.py`）的实际结构进行深度适配。
> **当前进度**: 第一、二阶段、前端联动（第三阶段一半）已完成 ✅ | 离线评测待启动

---

## 1. 核心痛点与重构愿景

### 1.1 当前痛点

| 痛点 | 代码映射 | 说明 |
|------|---------|------|
| **Agent 间无共享记忆** | `orchestrator.py:438` — `asyncio.gather` 并行执行后，结果仅通过 `AgentResult` 列表传递给 RCA | 各 Agent 相互独立，无法基于其他 Agent 的中间发现调整自身策略。RCA 只能做事后拼接，无法做过程协调 |
| **推理上下文不可追溯** | `AgentResult.detail` 为纯文本字符串 | Agent 的思考过程（"为什么选择关注 eMMC 而非网络"）不会被保存。复盘和评测时丢失了最有价值的推理链 |
| **可观测性受限** | `ThinkingProcess` 组件依赖 `<<<THINKING>>>` 标记 | 仅能展示LLM的输出片段，无法展示真正的排查进度（如"已排除3个假设，正在验证第4个"） |
| **RAG 架构预置缺失** | `vector_search.py` 当前为 TF-IDF baseline，尚未接入 embedding | 未来接入真实 RAG 后，检索到的碎片化文档缺乏与当前诊断上下文的关联机制。需要一个"热区"来承载当前任务的实时推理上下文 |

### 1.2 改造愿景：双轨并行 + 文件工作台

```
┌────────────────────────────────────────────────────────┐
│                    诊断任务上下文                        │
│                                                        │
│  ┌─────────────────┐      ┌──────────────────────┐     │
│  │  结构化轨道       │      │  Markdown 工作台轨道   │     │
│  │  (AgentResult)   │      │  (Workspace Files)   │     │
│  │                 │      │                      │     │
│  │  ✓ 置信度数值    │      │  ✓ 推理过程草稿       │     │
│  │  ✓ 引用来源列表  │      │  ✓ 排查清单 todo.md   │     │
│  │  ✓ 原始行号映射  │      │  ✓ 线索笔记 notes.md  │     │
│  │  ✓ 机器可解析    │      │  ✓ LLM 原生可读       │     │
│  └────────┬────────┘      └──────────┬───────────┘     │
│           │                          │                 │
│           └──────────┬───────────────┘                 │
│                      ▼                                 │
│              RCA Synthesizer                           │
│        (同时消费两条轨道的信息)                           │
└────────────────────────────────────────────────────────┘
```

**核心原则**：
- **不替代，只增强**：`AgentResult` dataclass 保持不变，继续承载结构化元数据（置信度、sources、raw_data）。Markdown 工作台作为补充层，承载 LLM 友好的推理过程和中间思考。
- **冷热分离**：pgvector / Jira Mock 数据 = 冷知识检索层；Markdown 工作区 = 当前任务的热状态层。
- **零侵入降级**：如果文件系统出现故障（磁盘满、权限异常），系统自动降级回纯 AgentResult 模式，不影响核心诊断流程。

---

## 2. 详细改造方案设计

### 2.1 新增模块规划

#### A. 工作区沙盒管理器 (`services/workspace_manager.py`)

```python
# 核心接口设计（伪代码）
class WorkspaceManager:
    """为每个诊断任务创建独立的 Markdown 工作区"""
    
    BASE_DIR = Path("backend/data/workspaces")
    
    def create(self, task_id: str) -> WorkspaceContext:
        """创建工作区，初始化模板文件"""
        # workspace_dir = BASE_DIR / task_id
        # 初始化: focus.md, notes.md, todo.md
    
    def append(self, task_id: str, file: str, section: str, content: str) -> None:
        """向指定文件的指定 section 追加内容（原子写入）"""
    
    def read(self, task_id: str, file: str) -> str:
        """读取指定文件全文"""
    
    def cleanup(self, task_id: str, archive: bool = False) -> None:
        """任务完成后清理或归档"""
```

**模板文件**：

| 文件 | 用途 | 写入者 |
|------|------|--------|
| `focus.md` | 当前任务总览：用户原始问题、已确认的 ECU、故障阶段 | Orchestrator 初始化 |
| `notes.md` | 各 Agent 的发现笔记，按 Agent 分 section | 各 Agent 独立写入各自 section |
| `todo.md` | 排查清单，用 `[ ]` / `[x]` 标记进度 | 各 Agent 更新自身负责的条目 |

#### B. Tool Use 扩展 (`services/tool_functions.py` 增补)

在现有的 `extract_timeline_events`、`fetch_raw_line_context` 等工具基础上，新增：

| 工具函数 | 功能 | 说明 |
|---------|------|------|
| `read_workspace_file` | 读取工作区文件 | Agent 在执行前读取 `focus.md` 理解全局上下文 |
| `append_workspace_notes` | 向 `notes.md` 追加发现 | 各 Agent 向自己的 section 写入分析发现 |
| `update_todo_status` | 更新 `todo.md` 中的打勾状态 | Agent 完成某项排查后标记 `[x]` |

**并发安全设计**：由于各 Agent 并行执行，写入操作必须保证线程安全：
- 各 Agent **只写自己的 section**（以 `## {agent_display_name}` 为分隔），不触碰其他 Agent 的区域。
- 使用 `asyncio.Lock` 保护每个文件的写入操作。
- `read` 操作无需加锁（读取快照即可）。

### 2.2 Orchestrator 执行流改造

> **重要约束**：保持现有的并行执行拓扑不变（`asyncio.gather`）。不引入串行依赖。

#### 改造前（当前流程）

```
用户提问
  ↓
Orchestrator (LLM 路由决策)
  ↓
┌──────────────────────────────────────┐
│  asyncio.gather (并行)                │
│  ├── LogAnalytics.execute()          │  → AgentResult
│  ├── JiraKnowledge.execute()         │  → AgentResult
│  └── DocRetrieval.execute()          │  → AgentResult
└──────────────────────────────────────┘
  ↓
RCA Synthesizer (遍历 AgentResult 列表)
  ↓
ResponseGenerator (LLM 生成最终报告)
```

#### 改造后（增加 Workspace 层）

```
用户提问
  ↓
Orchestrator 
  ├── 创建 Workspace (focus.md / notes.md / todo.md)
  └── LLM 路由决策
  ↓
┌──────────────────────────────────────────────────────┐
│  asyncio.gather (并行，与当前完全一致)                   │
│  ├── LogAnalytics.execute()                           │
│  │     ├── 返回 AgentResult (结构化通道，不变)           │
│  │     └── 写入 notes.md ## Log Analytics section      │
│  ├── JiraKnowledge.execute()                          │
│  │     ├── 返回 AgentResult                           │
│  │     └── 写入 notes.md ## Jira Knowledge section     │
│  └── DocRetrieval.execute()                           │
│        ├── 返回 AgentResult                           │
│        └── 写入 notes.md ## Doc Retrieval section      │
└──────────────────────────────────────────────────────┘
  ↓
RCA Synthesizer
  ├── 消费 AgentResult 列表 (结构化：置信度、sources)     ← 不变
  ├── 读取 notes.md 全文 (补充：推理过程、中间线索)         ← 新增
  └── 输出更连贯的综合诊断
  ↓
ResponseGenerator (不变)
  ↓
Workspace 清理 / 归档
```

**关键改造点**：

1. **`BaseAgent.execute()` 签名扩展**：在 `context` 字典中注入 `workspace_path`。

```python
# base.py 无需修改接口，通过 context 传递
context = {
    "agent_results": ...,          # 现有
    "workspace_path": "/data/workspaces/task_xxx",  # 新增
}
```

2. **各 Agent 的 `execute()` 实现改造**：在现有逻辑末尾增加可选的 workspace 写入。

```python
# 在各 Agent 的 execute() 末尾添加（伪代码）
if context and context.get("workspace_path"):
    workspace.append(
        task_id=...,
        file="notes.md",
        section=self.display_name,
        content=f"### 发现\n{analysis_summary}\n### 证据\n{evidence_lines}"
    )
```

3. **RCA Synthesizer 改造**：在现有的 `_synthesize_results` 基础上，额外读取 `notes.md`。

```python
# rca_synthesizer.py 改造（伪代码）
def _synthesize_results(self, task, agent_results, context):
    # 现有逻辑保持不变
    ...
    # 新增：读取 workspace 的推理笔记作为补充上下文
    workspace_notes = ""
    if context and context.get("workspace_path"):
        notes_path = Path(context["workspace_path"]) / "notes.md"
        if notes_path.exists():
            workspace_notes = notes_path.read_text()
    # 将 workspace_notes 注入 RCA 的分析 prompt 中
```

### 2.3 前端联动改造

**改造范围**：仅增强 `ThinkingProcess` 组件的信息密度，不引入人机交互编辑。

#### 当前 SSE 事件流（保持不变）：
```json
{"type": "step_start", "step": {"agentName": "Log Analytics", "status": "running"}}
{"type": "step_complete", "step": {"agentName": "Log Analytics", "result": "..."}}
```

#### 新增 SSE 事件类型（可选增强）：
```json
{"type": "workspace_update", "file": "todo.md", "agent": "Log Analytics", "change": "[x] 日志阶段验证完成"}
{"type": "workspace_update", "file": "notes.md", "agent": "Jira Knowledge", "change": "发现关联工单 FOTA-8765"}
```

**前端改造**：
- `ThinkingProcess.tsx` 在收到 `workspace_update` 事件时，在对应 Agent 步骤下方展示实时排查进度条目。
- **降级兼容**：如果后端未发送 `workspace_update` 事件，组件行为与当前完全一致。

---

## 3. 工程保障措施

### 3.1 降级策略

```python
# workspace_manager.py 核心保护逻辑
class WorkspaceManager:
    def create(self, task_id: str) -> WorkspaceContext | None:
        try:
            workspace_dir = self.BASE_DIR / task_id
            workspace_dir.mkdir(parents=True, exist_ok=True)
            # 初始化模板文件...
            return WorkspaceContext(workspace_dir)
        except (OSError, PermissionError) as e:
            log.warning("Workspace creation failed, degrading to pure AgentResult mode: %s", e)
            return None  # 返回 None 时，Orchestrator 跳过所有 workspace 逻辑
```

**降级矩阵**：

| 故障场景 | 降级行为 | 用户影响 |
|---------|---------|---------|
| 磁盘空间不足 | 跳过 Workspace 创建，纯 AgentResult 模式 | `ThinkingProcess` 无实时排查进度，但诊断结论不受影响 |
| 文件写入失败 | 捕获异常，继续执行，仅丢失笔记 | 同上 |
| 文件读取失败 | RCA Synthesizer 退回纯 AgentResult 分析 | 综合分析略少上下文，但核心推理不变 |

### 3.2 磁盘清理策略

| 策略 | 实现 | 触发条件 |
|------|------|---------|
| **即时清理** | 诊断完成后删除 workspace 目录 | 默认行为 |
| **延迟归档** | 将 workspace 压缩为 `.tar.gz` 移入 `data/workspaces_archive/` | 当 feedback 标记为 CONFIRMED |
| **定时清扫** | Cron 任务清理 7 天前的归档 | 每日凌晨 3:00 |
| **容量防护** | `WorkspaceManager.create()` 前检查 `data/workspaces/` 总大小，超过 1GB 时拒绝创建并报警 | 每次创建时 |

### 3.3 性能基准要求

改造完成后必须验证：

| 指标 | 基准阈值 | 测量方法 |
|------|---------|---------|
| Workspace 创建耗时 | < 5ms | `sync_step_timer` 包裹 |
| 单次文件写入耗时 | < 2ms | `asyncio.Lock` 持锁时间 |
| notes.md 全量读取耗时 | < 1ms（预估 < 50KB） | `async_step_timer` |
| 端到端诊断延迟增加 | < 3%（相比纯 AgentResult） | A/B 对比测试 |

### 3.4 与现有 `semantic_cache.py` 的集成

**原则**：缓存 key 与 workspace 完全解耦。

- 缓存 key = `SHA256(query + scenario_id)`，不包含 `task_id` 或 workspace 路径。
- 缓存命中时直接返回历史结果，**不创建 workspace**（无需重复分析）。
- 缓存未命中时正常创建 workspace 并执行诊断流程。
- 任务完成后，将最终诊断结论写入缓存，workspace 内容不进缓存。

---

## 4. 行动计划 (Phased Execution Timeline)

### 第一阶段：基础设施搭建（2 周） ✅ 已完成 (2026-04-06)

- [x] 新建 `services/workspace_manager.py`，实现 `create / append / read / cleanup` 四个核心方法
  - 实现了 `WorkspaceContext` 数据类（持有 per-file `asyncio.Lock`）
  - 实现了容量防护（`_check_capacity()`）、tar.gz 归档、统计信息（`get_stats()`）
  - 全局单例 `workspace_manager` 已导出
- [x] 在 `backend/data/workspaces` 下划分工作区目录，加入 `.gitignore`
  - 根 `.gitignore:57` 的 `data/` 规则已自动覆盖
- [x] 编写 `WorkspaceManager` 的单元测试（17/17 全部通过）
  - 覆盖：基础 CRUD、并发写入（3 Agent × 5 条）、section 隔离、降级场景、归档、todo 打勾
- [x] 在 `tool_functions.py` 中增加 `read_workspace_file`、`append_workspace_notes`、`update_todo_status`
- [x] 定义模板文件格式规范（`focus.md` / `notes.md` / `todo.md` 的 section 命名约定）
- [x] 在 `config.py` 中新增 `WORKSPACE_ENABLED: bool = True` 和 `WORKSPACE_MAX_SIZE_MB: int = 1024`

**验收结果**：17/17 测试用例全部通过，并发场景无数据竞争。

### 第二阶段：Agent 层适配（3 周） ✅ 已完成 (2026-04-06)

- [x] 修改 `orchestrator.py`：在 `orchestrate()` 函数开头创建 workspace（`uuid.uuid4` 生成 `task_id`），通过 `context` 注入 `workspace_path`
- [x] 修改 `LogAnalytics Agent`：新增 `_write_workspace()` 方法，写入 notes.md 的 `## Log Analytics Agent` section + 更新 todo “日志阶段验证”和“异常模式识别”
- [x] 修改 `JiraKnowledge Agent`：新增 `_write_workspace()` 方法，写入 notes.md 的 `## Maxus Jira Agent` section + 更新 todo “历史工单关联”
- [x] 修改 `DocRetrieval Agent`：新增 `_write_workspace()` 方法，写入 notes.md 的 `## Document Retrieval Agent` section + 更新 todo “技术文档匹配”
- [x] 修改 `RCA Synthesizer`：新增 `_read_workspace_notes()` 方法，在 `_synthesize_results` 中读取 notes.md 全文作为补充上下文
- [x] **保持 `AgentResult` dataclass 完全不变**，workspace 写入为可选增强
- [x] 在 `orchestrate()` 函数末尾添加 `workspace_manager.cleanup()` 调用
- [x] 补充 `workspace_update` SSE 事件的后端发射逻辑：新增 `_build_workspace_sse_events` 辅助函数从 markdown 文件增量提取进度

**验收结果**：
- 全部 import 无环依赖，4 个 Agent + Orchestrator 改造完毕
- 降级测试：所有 workspace 写入均在 `try/except` 中，失败仅产生 warning 日志
- `AgentResult` (base.py) 零修改
- 待LLM接入后进行端到端试跑

### 第三阶段：前端增强 + 评测验证（2 周） ✅ 全面完成 (2026-04-06)

- [x] 在 `lib/types.ts` 和 `page.tsx` 中增加对 `workspace_update` SSE 事件的解析和状态汇总
- [x] 在 `ThinkingProcess.tsx` 设计排查进度的 UI 呈现（新增 `WorkspacePanel` 子组件实现可折叠动画展示）
- [x] 降级兼容验证：后端不发送 `workspace_update` 时，前端退回纯 AgentResult 展示，无异常报错
- [x] 使用 `services/evaluation.py` 运行评测框架，对比改造前后的五维评分（在 Direct Agent Mock 模式下生成得分）
- [x] 撰写性能基准报告：输出至 `docs/Workspace评测基准报告.md`

**验收标准**：前端能实时精美展示排查进度 (`todo` 的 ✅/⬜，`notes` 的 📝)；评测总分不低于改造前。

---

## 5. 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 文件 I/O 拖慢诊断延迟 | 低 | 中 | 异步写入 + 延迟不超过 3% 的硬约束 |
| 并发写入导致 notes.md 乱序 | 中 | 低 | 各 Agent 写入独立 section + asyncio.Lock |
| Workspace 磁盘占用膨胀 | 中 | 中 | 容量防护 (1GB 上限) + 定时清扫 |
| RCA 读取 notes.md 产生幻觉 | 低 | 高 | notes.md 内容仅作辅助参考，AgentResult 仍为主数据源；引用断言验证 (`_validate_citations`) 持续生效 |
| 前端 SSE 新事件类型导致旧版本客户端异常 | 低 | 低 | 前端忽略未识别的事件类型（已有默认 `default: break` 逻辑） |

---

## 6. 与其他模块的兼容性

| 现有模块 | 影响 | 适配方式 |
|---------|------|---------|
| `AgentResult` (base.py) | **无变更** ✅ | 继续作为结构化数据通道 |
| `_validate_citations` (rca_synthesizer.py) | **无变更** ✅ | 引用验证仍基于 `AgentResult.sources`，不受 workspace 影响 |
| `semantic_cache.py` | **无变更** ✅ | 缓存 key 不含 workspace 信息 |
| `api/feedback.py` | **待微调** | 当 feedback 为 CONFIRMED 时触发 workspace 归档 |
| `api/metrics.py` | **待微调** | 新增 `fota_workspace_created_total` 和 `fota_workspace_io_seconds` 指标 |
| `config.py` | **已完成** ✅ | 新增 `WORKSPACE_ENABLED: bool = True` 和 `WORKSPACE_MAX_SIZE_MB: int = 1024` |

---

## 7. 相关文档

- [CLAUDE.md](../CLAUDE.md) — 项目架构总览与编码规范
- [TODO.md](./TODO.md) — 开发进度跟踪
- [MVP实施总结报告](./MVP实施总结报告.md) — 当前 Agent 架构的实现细节
- [演示操作指南](./演示操作指南.md) — 端到端演示流程

---

**文档维护**: FOTA 诊断平台团队
**审核状态**: v2.2 — 代码开发全部完成（基础设施、Agent 后端、SSE 串联、前端 UI 展示），下一步为评估测试
