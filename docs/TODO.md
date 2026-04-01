# Velab 第一期基础 Demo 架构完成任务清单

该 TODO 列表旨在将当前的 Mock 原型演进为可实际演示的「FOTA 智能诊断平台」基础架构。按照 **后端(API) -> 中转(Gateway) -> 前端(UI) -> 数据(Data)** 的顺序排列。

## 1. 基础设施与环境 (P0)
- [ ] **.env 环境补齐**: 
    - [ ] 创建 `backend/.env` 并填入 MiniMax API Key。
    - [ ] 创建 `gateway/.env` 并填入各模型 API Key。
- [ ] **Gateway 联调**: 
    - [ ] 启动 `litellm` 代理服务器，验证 `minimax-m2-5` 接口转发是否通畅。
    - [ ] 验证 `claude-3-5-sonnet` 的 Fallback 机制是否能正确触发。
- [ ] **Python 依赖安装**: 
    - [ ] `pip install -r backend/requirements.txt`。
    - [ ] 安装额外组件: `pip install litellm sse-starlette`。

## 2. 后端核心逻辑优化 (P1)
- [ ] **Orchestrator 意图识别加固**: 
    - [ ] 在 `orchestrator.py` 中增加对「ECU 刷写顺序」和「OTA 回退」相关语义的识别 Prompt。
    - [ ] 优化 `DEFAULT_CLARIFICATION_REPLY`，使其能根据车型自动调整引导内容。
- [ ] **Log Analytics Agent 语义化**: 
    - [ ] 实现基础的「时间窗口裁剪」逻辑：根据用户提到的时间点，只读取前后 15 分钟的日志片段送入 LLM。
    - [ ] 接入 `services/llm.py`，将提取出的日志内容发送给模型进行真实推理，而非仅使用 `_mock_analyze`。
- [ ] **Jira Knowledge Agent RAG 化**: 
    - [ ] 在 `services/` 下新增 `vector_search.py` (Mock 版本)，模拟从向量数据库检索相关工单。
    - [ ] 补充更多 FOTA 典型的故障案例 (如: eMMC 写入报错、T-Box 掉线、校验和不匹配)。

## 3. 前端交互功能开发 (P1)
- [ ] **SSE 流式渲染优化**: 
    - [ ] 确保 `<<<THINKING>>>` 标记的内容能以灰色折叠框形式展示。
    - [ ] 支持渲染 Markdown 格式的诊断报告（包含表格和置信度标签）。
- [ ] **引用来源面板**: 
    - [ ] 点击诊断报告中的引用来源时，右侧能弹出浮窗展示对应的日志片段或 Jira 描述。
- [ ] **执行状态 Timeline**: 
    - [ ] 展示 Orchestrator 调度各 Agent 的动态过程（Log Agent: Analyzing... -> Done）。

## 4. 数据与演示场景准备 (P2)
- [ ] **演示日志集**: 
    - [ ] 在 `data/logs/` 放置 3-5 个典型的 FOTA 故障日志样本（文本格式）。
- [ ] **场景引导词**: 
    - [ ] 预设 3 个引导提问，如：「分析为何 iCGM 在 11:24 发生心跳丢失」、「查询类似 FOTA-9123 的历史案例」。

## 5. 生产化准备 (P3)
- [ ] **Systemd 部署配置文件**: 
    - [ ] 编写 `velab-backend.service`。
    - [ ] 编写 `velab-gateway.service`。
- [ ] **Nginx 反向代理配置**: 
    - [ ] 配置 `/api` 转发到后端，其余转发到 Next.js 前端。

---
*注：优先完成 P0 和 P1 任务，即可达到 demo 视频中的演示水平。*