# FOTA 智能诊断平台 - 项目文档

## 项目概述

FOTA（Firmware Over-The-Air）智能诊断平台是一个基于 AI 的车辆固件升级诊断系统，通过多 Agent 协作分析车辆升级日志、历史工单和技术文档，为技术人员提供智能化的故障诊断和解决方案。

### 核心特性

- **多 Agent 协作架构**：可扩展的插件式 Agent 系统
- **实时流式响应**：基于 SSE 的流式诊断过程展示
- **场景化诊断**：支持多种诊断场景（FOTA 诊断、Jira 工单、车队分析等）
- **智能编排**：LLM 驱动的 Agent 自动选择和并行执行
- **敏感信息保护**：自动脱敏 VIN 码、手机号、车牌号等敏感数据

## 技术架构

### 后端技术栈

- **框架**: FastAPI（异步 Web 框架）
- **LLM 集成**: OpenAI SDK + LiteLLM 网关
- **配置管理**: Pydantic Settings
- **日志追踪**: 全链路 trace_id 追踪
- **流式响应**: SSE (Server-Sent Events)

### 前端技术栈

- **框架**: Next.js 14 (App Router)
- **语言**: TypeScript
- **样式**: Tailwind CSS + CSS Variables
- **状态管理**: React Hooks
- **实时通信**: SSE 流式接收

### 部署架构

支持两种部署模式：

1. **场景 A（国内部署）**
   - 通过 LiteLLM 网关中转访问 LLM 服务
   - 统一 API 密钥管理
   - 支持多供应商负载均衡

2. **场景 B（海外部署）**
   - 直连 LLM 供应商 API
   - 降低延迟
   - 简化架构

## 项目结构

```
Velab/
├── backend/                 # FastAPI 后端服务
│   ├── agents/             # Agent 插件目录
│   │   ├── base.py         # Agent 基类和注册表
│   │   ├── orchestrator.py # 智能编排器
│   │   ├── log_analytics.py # 日志分析 Agent
│   │   └── jira_knowledge.py # Jira 知识库 Agent
│   ├── common/             # 公共模块
│   │   ├── chain_log.py    # 调用链日志
│   │   └── redaction.py    # 敏感信息脱敏
│   ├── services/           # 服务层
│   │   └── llm.py          # LLM 统一客户端
│   ├── config.py           # 配置管理
│   └── main.py             # FastAPI 应用入口
├── web/                    # Next.js 前端应用
│   ├── src/
│   │   ├── app/            # App Router 页面
│   │   │   ├── api/chat/   # API 路由（代理层）
│   │   │   └── page.tsx    # 主页面
│   │   └── components/     # React 组件
│   │       ├── ChatMessage.tsx    # 消息组件
│   │       ├── ThinkingProcess.tsx # 思考过程展示
│   │       ├── InputBar.tsx       # 输入框
│   │       └── Header.tsx         # 页头
├── gateway/                # LiteLLM 网关配置
│   ├── config.yaml         # 网关配置文件
│   ├── nginx/              # Nginx 反向代理配置
│   └── scripts/            # 启动脚本
└── docs/                   # 项目文档
```

## 核心模块说明

### 1. Agent 系统 ([`backend/agents/`](backend/agents/))

#### 基础架构 ([`base.py`](backend/agents/base.py))

- **AgentResult**: 标准化的 Agent 执行结果数据类
- **BaseAgent**: 所有 Agent 的抽象基类
- **AgentRegistry**: 全局 Agent 注册表，支持自动发现

#### 智能编排器 ([`orchestrator.py`](backend/agents/orchestrator.py))

核心功能：
- 分析用户问题，理解诊断需求
- 通过 LLM function-calling 选择合适的 Agent
- 并行执行多个 Agent
- 聚合结果并生成结构化回复

关键方法：
- `orchestrate()`: 主编排流程，yield SSE 事件
- `generate_final_response()`: 生成最终诊断报告

#### 日志分析 Agent ([`log_analytics.py`](backend/agents/log_analytics.py))

功能：
- 加载和解析 FOTA 升级日志
- 根据关键词过滤相关日志
- 分析异常时间线、错误码和故障根因

#### Jira 知识库 Agent ([`jira_knowledge.py`](backend/agents/jira_knowledge.py))

功能：
- 检索历史 Jira 工单
- 搜索离线技术文档
- 提供类似故障案例和修复方案

### 2. LLM 服务层 ([`backend/services/llm.py`](backend/services/llm.py))

统一的 LLM 客户端，支持：
- 多供应商切换（OpenAI、Anthropic 等）
- 阻塞式和流式调用
- Function calling 解析
- 敏感信息自动脱敏
- 全链路日志追踪

关键方法：
- `chat_completion()`: 阻塞式对话完成
- `chat_completion_stream()`: 流式对话完成
- `get_embeddings()`: 获取文本向量嵌入
- `parse_tool_calls()`: 解析 function calling 结果

### 3. 配置管理 ([`backend/config.py`](backend/config.py))

使用 Pydantic Settings 管理配置：
- 支持 `.env` 文件和环境变量
- 自动类型验证
- 派生属性（DATABASE_URL、LLM_BASE_URL 等）
- 场景化 Agent 映射

### 4. 调用链日志 ([`backend/common/chain_log.py`](backend/common/chain_log.py))

全链路日志追踪系统：
- 基于 contextvars 的 trace_id 传递
- 统一的日志格式（包含时间戳、步骤、事件）
- 异步和同步计时器装饰器
- ISO 8601 UTC 时间戳

### 5. 敏感信息脱敏 ([`backend/common/redaction.py`](backend/common/redaction.py))

自动脱敏模块：
- VIN 码识别和替换
- 手机号识别和替换
- 车牌号识别和替换
- 装饰器自动拦截 LLM 输入输出

### 6. 前端主页面 ([`web/src/app/page.tsx`](web/src/app/page.tsx))

核心功能：
- 场景选择和切换
- 消息历史管理
- SSE 流式接收和解析
- 实时更新 UI（Thinking Process、内容增量）
- 中断控制

### 7. 聊天消息组件 ([`web/src/components/ChatMessage.tsx`](web/src/components/ChatMessage.tsx))

功能：
- 轻量级 Markdown 渲染器
- 用户/助手消息样式区分
- Thinking Process 展示
- 流式输出光标动画
- 反馈按钮

## 开发指南

### 环境准备

1. **后端环境**
```bash
cd Velab/backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **前端环境**
```bash
cd Velab/web
npm install
```

3. **配置文件**

复制 `.env.example` 并修改：
```bash
# 后端
cp backend/.env.example backend/.env

# 网关
cp gateway/.env.example gateway/.env
```

### 启动服务

1. **启动后端**
```bash
cd Velab/backend
python main.py
# 或使用 uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

2. **启动前端**
```bash
cd Velab/web
npm run dev
```

3. **启动 LiteLLM 网关**（场景 A）
```bash
cd Velab/gateway
./scripts/start.sh
```

### 添加新 Agent

1. 在 `backend/agents/` 创建新文件，如 `my_agent.py`
2. 继承 `BaseAgent` 并实现 `execute()` 方法
3. 在文件末尾注册：`registry.register(MyAgent())`
4. 在 `backend/main.py` 导入模块触发注册
5. 在 `config.py` 的 `SCENARIO_AGENT_MAP` 中配置场景映射

示例：
```python
from agents.base import BaseAgent, AgentResult, registry

class MyAgent(BaseAgent):
    name = "my_agent"
    display_name = "My Custom Agent"
    description = "Agent 功能描述"
    
    async def execute(self, task: str, keywords: list[str] | None = None, context: dict | None = None) -> AgentResult:
        # 实现诊断逻辑
        return AgentResult(
            agent_name=self.name,
            display_name=self.display_name,
            success=True,
            confidence="high",
            summary="分析摘要",
            detail="详细分析结果",
            sources=[{"title": "来源", "type": "log"}]
        )

registry.register(MyAgent())
```

## 部署指南

### Docker 部署

```bash
# 构建镜像
docker build -t fota-backend ./backend
docker build -t fota-web ./web

# 运行容器
docker run -d -p 8000:8000 --env-file backend/.env fota-backend
docker run -d -p 3000:3000 --env-file web/.env fota-web
```

### Systemd 服务

参考配置文件：
- 后端：[`backend/systemd/fota-backend.service`](backend/systemd/fota-backend.service)
- 网关：[`gateway/systemd/litellm.service`](gateway/systemd/litellm.service)

### Nginx 反向代理

参考配置文件：
- 后端：[`backend/nginx/backend.conf`](backend/nginx/backend.conf)
- 网关：[`gateway/nginx/litellm.conf`](gateway/nginx/litellm.conf)

## API 文档

### POST /chat

诊断对话接口（SSE 流式响应）

**请求体**:
```json
{
  "message": "用户的诊断问题",
  "scenarioId": "fota-diagnostic",
  "history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

**响应格式**（SSE 事件流）:
```
data: {"type": "step_start", "step": {...}}
data: {"type": "step_complete", "step": {...}}
data: {"type": "content_delta", "content": "..."}
data: {"type": "content_complete", "sources": [...], "confidenceLevel": "高"}
data: {"type": "done"}
```

### GET /health

健康检查接口

**响应**:
```json
{
  "status": "ok",
  "agents": [
    {"name": "log_analytics", "display_name": "Log Analytics Agent"},
    {"name": "jira_knowledge", "display_name": "Maxus Jira Agent"}
  ]
}
```

## 配置说明

### 环境变量

#### 后端 (`backend/.env`)

```bash
# 部署模式：A=国内中转，B=海外直连
DEPLOYMENT_MODE=A

# LiteLLM 网关配置（场景 A）
LITELLM_BASE_URL=https://gateway.fota.com/v1
LITELLM_API_KEY=sk-fota-master-key

# 直连供应商配置（场景 B）
ANTHROPIC_API_KEY=sk-ant-xxx
OPENAI_API_KEY=sk-xxx

# 数据库配置（待接入）
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=fota_password
POSTGRES_DB=fota_db

# Redis 配置（待接入）
REDIS_HOST=localhost
REDIS_PORT=6379

# 日志级别
LOG_LEVEL=DEBUG
```

#### 前端 (`web/.env.local`)

```bash
# 后端服务地址
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
BACKEND_URL=http://localhost:8000
```

#### 网关 (`gateway/.env`)

```bash
LITELLM_MASTER_KEY=sk-fota-master-key
LITELLM_LOG_LEVEL=INFO
```

### LiteLLM 网关配置 (`gateway/config.yaml`)

```yaml
model_list:
  - model_name: router-model
    litellm_params:
      model: anthropic/claude-3-5-sonnet-20241022
      api_key: os.environ/ANTHROPIC_API_KEY
  
  - model_name: agent-model
    litellm_params:
      model: anthropic/claude-3-5-sonnet-20241022
      api_key: os.environ/ANTHROPIC_API_KEY

router_settings:
  routing_strategy: simple-shuffle
  num_retries: 2
  timeout: 120
```

## 日志格式

所有日志遵循统一格式：

```
2025-01-15T10:30:45.123 DEBUG [module_name] [CHAIN] trace=abc123 step=orchestrate event=START ts=2025-01-15T10:30:45.123Z user_len=50
```

关键字段：
- `trace`: 请求唯一标识符
- `step`: 执行步骤（如 orchestrate、llm.chat_completion）
- `event`: 事件类型（START、END、ERROR 等）
- `ts`: ISO 8601 UTC 时间戳
- `elapsed_ms`: 耗时（毫秒）

## 故障排查

### 常见问题

1. **LLM 调用失败**
   - 检查 API 密钥配置
   - 确认网络连接（场景 A 检查网关，场景 B 检查直连）
   - 查看日志中的 `llm.chat_completion` 步骤

2. **Agent 未注册**
   - 确认 Agent 模块已在 `main.py` 中导入
   - 检查 `registry.register()` 是否执行
   - 访问 `/health` 端点查看已注册 Agent

3. **SSE 连接中断**
   - 检查前端超时配置（默认 120 秒）
   - 查看后端日志中的 `http.chat` 步骤
   - 确认 Nginx 配置支持 SSE（proxy_buffering off）

4. **敏感信息泄露**
   - 确认 `@sensitive_redactor` 装饰器已应用
   - 检查日志输出是否包含 `[REDACTED_VIN]` 等标记
   - 验证正则表达式匹配规则

## 性能优化

### 后端优化

1. **并行执行 Agent**
   - 使用 `asyncio.gather()` 并行调用多个 Agent
   - 减少总体响应时间

2. **流式响应**
   - 启用 `ORCHESTRATOR_STREAM=True`
   - 降低首字节时间（TTFB）

3. **缓存策略**
   - 缓存常见问题的 Agent 结果
   - 使用 Redis 存储会话历史

### 前端优化

1. **虚拟滚动**
   - 对长对话历史使用虚拟列表
   - 减少 DOM 节点数量

2. **代码分割**
   - 按路由分割代码
   - 懒加载非关键组件

3. **SSE 缓冲优化**
   - 批量处理 SSE 事件
   - 减少状态更新频率

## 安全建议

1. **API 密钥管理**
   - 使用环境变量存储密钥
   - 定期轮换密钥
   - 限制密钥权限范围

2. **敏感数据保护**
   - 启用自动脱敏功能
   - 定期审计日志输出
   - 加密存储历史对话

3. **访问控制**
   - 配置 CORS 白名单
   - 实施 API 速率限制
   - 添加身份认证中间件

4. **日志安全**
   - 避免记录完整请求体
   - 脱敏后再写入日志
   - 定期清理旧日志

## 测试

### 单元测试

```bash
cd Velab/backend
pytest tests/
```

### 集成测试

```bash
# 启动所有服务后
cd Velab/backend
pytest tests/integration/
```

### 前端测试

```bash
cd Velab/web
npm test
```

---

**注意**: 本文档会随项目更新持续维护，请定期查看最新版本。
