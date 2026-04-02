# FOTA 诊断平台 — LLM API 中转方案

> **文档定位**：作为《FOTA 多域日志智能诊断系统可行性方案（修订版 v6）》的补充文档，专门解决 LLM API 的网络通路和中转架构问题。
>
> **核心问题**：Claude（Anthropic）和 OpenAI 的 API 服务器部署在海外，中国大陆无法直接访问。需要设计 API 中转方案，覆盖两种部署场景。

---

## 1. 方案 v6 中 LLM API 调用清单

从方案 v6 中抽取所有需要调用 LLM API 的环节：

| 调用环节 | 主力模型（Claude） | Fallback 模型（OpenAI） | 调用模式 | 频次特征 |
|---|---|---|---|---|
| 意图路由（§5） | Claude Haiku 4.5 | GPT-5.4-nano | chat, 极短输出 | 每次诊断 1 次 |
| Log Analytics Agent（§8.1） | Claude Sonnet 4.6 | GPT-5.4-mini | chat + tool_use + streaming | 每次诊断 3~8 轮 |
| Jira Agent（§8.2） | Claude Sonnet 4.6 | GPT-5.4-mini | chat + tool_use + streaming | 每次诊断 2~5 轮 |
| Doc Agent（§8.3） | Claude Sonnet 4.6 | GPT-5.4-mini | chat + tool_use + streaming | 每次诊断 1~3 轮 |
| RCA Synthesizer（§8.4） | Claude Sonnet/Opus 4.6 | GPT-5.4 | chat + streaming（长输出） | 每次诊断 1 次 |
| Embedding 向量化（§2） | — | text-embedding-3-large | embedding 批量 | 离线，大批量 |

**协议要求**：
- Anthropic API：`api.anthropic.com`，使用 Anthropic 原生格式（Messages API）
- OpenAI API：`api.openai.com`，使用 OpenAI Chat Completions 格式
- 两种格式**不兼容**，中转层需要处理或透传

---

## 2. 两种部署场景

### 场景 A：FOTA 平台部署在中国大陆

```
适用情况：
- 企业服务器/机房在国内
- 用户（工程师）在国内办公网络访问
- 日志数据不出境（合规优先）
- 只有 LLM 推理调用需要走海外
```

### 场景 B：开发阶段在中国，生产环境部署在海外

```
适用情况：
- 开发团队在中国大陆
- 生产环境部署在海外云（AWS/GCP 东京/新加坡/美西）
- 生产环境可直连 Claude/OpenAI API
- 开发/测试环境需要中转
```

---

## 3. 场景 A 方案：平台在国内，LLM API 中转在海外

### 3.1 架构总览

```mermaid
flowchart LR
    subgraph 中国大陆
        FOTA[FOTA 诊断平台<br/>FastAPI + Agents]
        DB[(PostgreSQL<br/>pgvector)]
        REDIS[(Redis)]
        MINIO[(MinIO)]
    end

    subgraph 美国 CN2 GIA 服务器
        LITELLM[LiteLLM Proxy<br/>:4000<br/>统一 OpenAI 格式<br/>pip + systemd 部署]
    end

    subgraph LLM 供应商（美国）
        CLAUDE[api.anthropic.com<br/>Claude API]
        OPENAI[api.openai.com<br/>OpenAI API]
    end

    FOTA -->|HTTPS ~150ms<br/>统一 OpenAI 格式| LITELLM
    LITELLM -->|同区域直连 <10ms| CLAUDE
    LITELLM -->|同区域直连 <10ms| OPENAI

    FOTA --- DB
    FOTA --- REDIS
    FOTA --- MINIO
```

### 3.2 核心设计决策

**中转层采用 LiteLLM Proxy（智能网关），而非哑管道转发。**

理由：

| 考量 | 哑管道（Nginx/CF Worker） | LiteLLM 智能网关 |
|---|---|---|
| 跨境网络不稳定时的 Fallback | 做不了，FOTA 平台自己处理 Fallback 时要再发一个跨境请求 | **LiteLLM 在海外本地 Fallback**，一次跨境请求搞定 |
| Key Pool 轮转 | 需要跨境传递 Key 选择信息 | **LiteLLM 在海外本地轮转**，FOTA 只发一个 virtual key |
| 429 重试 | FOTA 每次重试都要跨境 | **LiteLLM 在海外本地重试**，跨境只走一次 |
| API 格式转换 | 需要分别适配 Claude/OpenAI 格式 | **LiteLLM 统一转为 OpenAI 格式**，FOTA 只用一种 SDK |

**关键洞察**：跨境网络是最脆弱的一环。把「重试/Fallback/Key 轮转」放在海外端，可以**最大限度减少跨境请求次数**。一次跨境请求到 LiteLLM，LiteLLM 在海外本地完成所有容错逻辑。

### 3.3 对方案 v6 的改动

| 方案 v6 原设计 | 场景 A 改动 | 说明 |
|---|---|---|
| §4.2 `LLMProvider` Protocol<br/>`ClaudeProvider` / `OpenAIProvider` | **删除**，替换为统一的 `openai.AsyncOpenAI(base_url=中转地址)` | LiteLLM 对外只暴露 OpenAI 格式，无需区分供应商 |
| §4.2 `llm_config` 字典<br/>（primary/fallback 配置） | **迁移到** LiteLLM `config.yaml` | 模型选择、Fallback 链在中转层配置 |
| §10 429 五层防御<br/>（Cache, Queue, KeyPool, Fallback, CircuitBreaker） | **L2-L4 迁移到** LiteLLM<br/>L1（语义缓存）与 L5（业务级熔断降级）保留在 FOTA 平台 | LiteLLM 原生支持 Key 轮转、重试、Fallback、并发控制及网关级熔断 |
| §4.3 数据安全<br/>（日志脱敏、只送摘要） | **保留不变** | 严禁原始日志包出境。仅脱敏后的分析片段随请求出境，脱敏在 FOTA 平台完成 |
| §10.3 可观测性<br/>（LLM 调用指标） | **部分迁移到** LiteLLM Prometheus metrics | LiteLLM 内置 `litellm_requests_total`、`litellm_spend_total` 等 |

### 3.4 FOTA 平台侧代码改造

改造后，FOTA 平台所有 LLM 调用统一使用 `openai` SDK：

```python
# fota/llm/client.py — 统一 LLM 客户端（替代原 LLMProvider 抽象层）
import openai
from fota.config import settings

# 唯一的 LLM 客户端实例，指向海外 LiteLLM Proxy
llm_client = openai.AsyncOpenAI(
    api_key=settings.LITELLM_API_KEY,       # LiteLLM virtual key
    base_url=settings.LITELLM_BASE_URL,     # https://llm-proxy.example.com/v1
    timeout=120.0,
    max_retries=1,                           # FOTA 侧只重试 1 次（网络层），
                                             # LLM 层重试由 LiteLLM 在海外处理
)

# === 路由层调用 ===
async def route_query(query: str) -> dict:
    response = await llm_client.chat.completions.create(
        model="router-model",               # LiteLLM 中配置的 model_name
        messages=[{"role": "user", "content": query}],
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)

# === Agent 调用（含 Tool Use + Streaming）===
async def call_agent(messages: list, tools: list):
    response = await llm_client.chat.completions.create(
        model="agent-model",                 # LiteLLM 路由到 Claude Sonnet → Fallback OpenAI
        messages=messages,
        tools=tools,
        stream=True,
    )
    async for chunk in response:
        yield chunk

# === Embedding 调用 ===
async def embed_texts(texts: list[str]) -> list[list[float]]:
    response = await llm_client.embeddings.create(
        model="embedding-model",
        input=texts,
    )
    return [item.embedding for item in response.data]
```

**关键简化**：
- ❌ 不再 import `anthropic` SDK
- ❌ 不再需要 `ClaudeProvider` / `OpenAIProvider` 两套实现
- ❌ 不再需要在 FOTA 代码中处理 Fallback/Key Pool/限流
- ✅ 所有调用走同一个 `llm_client`，3 个 model name 区分用途

### 3.5 跨境网络稳定性保障

中国大陆到海外中转的网络链路是整个架构最大的风险点。

**服务器选型**：使用现有美国 CN2 GIA 服务器资源。

| 链路 | 延迟 | 说明 |
|---|---|---|
| 中国大陆 → 美国 CN2 GIA | ~130-180ms | 跨境唯一一跳 |
| 美国 VPS → Claude API（美国） | < 10ms | 同区域直连 |
| 美国 VPS → OpenAI API（美国） | < 10ms | 同区域直连 |

**优势**：Claude 和 OpenAI API 服务器都在美国，LiteLLM 部署在同区域，Fallback/重试零延迟。多台服务器资源可做高可用。

**FOTA 平台侧的超时与重试策略**：

```python
# fota/config.py
class Settings:
    LITELLM_BASE_URL: str = "https://llm-proxy.example.com/v1"
    LITELLM_API_KEY: str = "sk-fota-virtual-key"

    # 跨境网络超时（比直连要宽松）
    LLM_CONNECT_TIMEOUT: float = 10.0       # 建连超时（跨境可能较慢）
    LLM_READ_TIMEOUT: float = 120.0         # 读取超时（streaming 长输出）
    LLM_MAX_RETRIES: int = 1                # FOTA 侧网络重试（非 LLM 重试）

    # 跨境连接池（保持长连接减少握手）
    LLM_MAX_CONNECTIONS: int = 20
    LLM_MAX_KEEPALIVE: int = 10
```

**长连接优化**：FOTA 到 LiteLLM 保持 HTTP/2 长连接池，避免每次请求都做 TLS 握手（跨境 TLS 握手可能需要 200ms+）。

---

## 4. 场景 B 方案：开发在国内，生产在海外

### 4.1 架构总览

```mermaid
flowchart TB
    subgraph 生产环境（海外云）
        FOTA_PROD[FOTA 诊断平台<br/>FastAPI + Agents]
        DB_PROD[(PostgreSQL + pgvector)]
        REDIS_PROD[(Redis)]
        MINIO_PROD[(MinIO / S3)]
    end

    subgraph LLM 供应商
        CLAUDE[api.anthropic.com]
        OPENAI[api.openai.com]
    end

    FOTA_PROD -->|直连<br/>无中转| CLAUDE
    FOTA_PROD -->|直连<br/>无中转| OPENAI

    subgraph 开发环境（中国大陆）
        DEV[开发者本机<br/>FOTA 开发调试]
        LITELLM_DEV[LiteLLM Proxy<br/>海外 VPS / CF Worker<br/>仅开发用]
    end

    DEV -->|HTTPS| LITELLM_DEV
    LITELLM_DEV -->|直连| CLAUDE
    LITELLM_DEV -->|直连| OPENAI
```

### 4.2 核心设计

**生产环境不需要中转**：FOTA 平台和 LLM API 都在海外，直连即可。

**开发环境需要中转**：开发者在中国，调试时需要调 LLM API。

这意味着架构设计上要**兼容两种模式**：

```python
# fota/config.py — 通过环境变量切换模式
class Settings:
    # 生产环境：直连 Claude/OpenAI
    # 开发环境：通过中转代理
    DEPLOYMENT_MODE: str = "production"  # "production" | "development"

    # LLM 配置
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com"    # 生产默认值
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"       # 生产默认值

    # 开发环境中转（仅 DEPLOYMENT_MODE=development 时使用）
    LITELLM_BASE_URL: str = ""           # 如 https://dev-llm-proxy.example.com/v1
    LITELLM_API_KEY: str = ""
```

### 4.3 生产环境：保留方案 v6 原始设计

生产环境在海外直连，**保留方案 v6 的 `LLMProvider` 抽象层**：

```python
# fota/llm/provider.py — 方案 v6 §4.2 原设计，生产环境使用
from typing import Protocol

class LLMProvider(Protocol):
    async def chat(self, messages: list[dict], tools: list[dict] | None = None,
                   stream: bool = False, **kwargs) -> ChatResponse: ...
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

class ClaudeProvider(LLMProvider):
    """直连 Anthropic API — 生产环境主力"""
    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com"):
        self.client = anthropic.AsyncAnthropic(api_key=api_key, base_url=base_url)

    async def chat(self, messages, tools=None, stream=False, **kwargs):
        # 调用 Anthropic Messages API，转换格式
        response = await self.client.messages.create(
            model=kwargs.get("model", "claude-sonnet-4-6-20260301"),
            messages=messages,
            tools=tools,
            stream=stream,
            max_tokens=kwargs.get("max_tokens", 8192),
        )
        return self._normalize_response(response)

class OpenAIProvider(LLMProvider):
    """直连 OpenAI API — 生产环境 Fallback + Embedding"""
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        self.client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def chat(self, messages, tools=None, stream=False, **kwargs):
        response = await self.client.chat.completions.create(
            model=kwargs.get("model", "gpt-5.4-mini"),
            messages=messages,
            tools=tools,
            stream=stream,
        )
        return self._normalize_response(response)

    async def embed(self, texts):
        response = await self.client.embeddings.create(
            model="text-embedding-3-large", input=texts
        )
        return [item.embedding for item in response.data]
```

Fallback 逻辑在 FOTA 代码内部实现（方案 v6 §10 的 429 防御方案）：

```python
# fota/llm/router.py — 生产环境的 Fallback 路由
class LLMRouter:
    def __init__(self, primary: LLMProvider, fallback: LLMProvider):
        self.primary = primary
        self.fallback = fallback

    async def chat(self, messages, tools=None, stream=False, **kwargs):
        for attempt, provider in enumerate([self.primary, self.fallback]):
            try:
                return await provider.chat(messages, tools, stream, **kwargs)
            except (RateLimitError, APITimeoutError, InternalServerError) as e:
                logger.warning(f"Provider {attempt} failed: {e}")
                if attempt == 0:
                    continue  # 切 fallback
                raise  # 两个都失败
```

### 4.4 开发环境：通过 LiteLLM 中转

开发者在中国大陆，无法直连 Claude/OpenAI。通过环境变量切换到 LiteLLM 中转模式：

```python
# fota/llm/factory.py — 根据部署模式创建 LLM 客户端
def create_llm_router(settings: Settings) -> LLMRouter:
    if settings.DEPLOYMENT_MODE == "production":
        # 生产环境：直连，使用方案 v6 原始设计
        primary = ClaudeProvider(
            api_key=settings.ANTHROPIC_API_KEY,
            base_url=settings.ANTHROPIC_BASE_URL,
        )
        fallback = OpenAIProvider(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )
        return LLMRouter(primary=primary, fallback=fallback)

    elif settings.DEPLOYMENT_MODE == "development":
        # 开发环境：通过 LiteLLM 中转，统一走 OpenAI 格式
        # LiteLLM 已处理 Fallback/限流，这里不需要双 Provider
        proxy_provider = OpenAIProvider(
            api_key=settings.LITELLM_API_KEY,
            base_url=settings.LITELLM_BASE_URL,
        )
        # primary 和 fallback 都指向 LiteLLM（LiteLLM 内部处理 Fallback）
        return LLMRouter(primary=proxy_provider, fallback=proxy_provider)
```

开发环境的 `.env`：
```bash
# .env.development
DEPLOYMENT_MODE=development
LITELLM_BASE_URL=https://dev-llm-proxy.example.com/v1
LITELLM_API_KEY=sk-dev-virtual-key
```

生产环境的 `.env`：
```bash
# .env.production
DEPLOYMENT_MODE=production
ANTHROPIC_API_KEY=sk-ant-xxxxx
ANTHROPIC_BASE_URL=https://api.anthropic.com
OPENAI_API_KEY=sk-xxxxx
OPENAI_BASE_URL=https://api.openai.com/v1
```

### 4.5 场景 B 总结

```
生产环境（海外）：
  FOTA 平台 → 直连 Claude/OpenAI API
  保留方案 v6 全部设计（LLMProvider / Fallback / 429 防御）
  零中转，零额外延迟

开发环境（中国）：
  开发者本机 → LiteLLM Proxy（海外 VPS）→ Claude/OpenAI API
  通过 DEPLOYMENT_MODE 环境变量切换
  LiteLLM 处理 Fallback/限流，开发者无感
```

---

## 5. LiteLLM Proxy 部署实现（pip + systemd 原生部署）

以下配置同时适用于场景 A 的生产中转和场景 B 的开发中转。部署目标为美国 CN2 GIA 服务器（Linux）。

### 5.1 目录结构

```
/opt/litellm-proxy/
├── config.yaml                 # LiteLLM 模型路由配置
├── .env                        # API Keys（chmod 600，不入版本库）
├── start.sh                    # 启动脚本
└── logs/                       # 日志目录
    └── litellm.log
```

### 5.2 安装

```bash
# 1. 创建专用用户（安全隔离）
sudo useradd -r -s /sbin/nologin litellm
sudo mkdir -p /opt/litellm-proxy/logs
sudo chown -R litellm:litellm /opt/litellm-proxy

# 2. 创建 Python 虚拟环境
sudo -u litellm python3 -m venv /opt/litellm-proxy/venv

# 3. 安装 LiteLLM（proxy 模式）
sudo -u litellm /opt/litellm-proxy/venv/bin/pip install 'litellm[proxy]'

# 4. 验证安装
sudo -u litellm /opt/litellm-proxy/venv/bin/litellm --version
```

### 5.3 LiteLLM 配置文件

```yaml
# /opt/litellm-proxy/config.yaml
# FOTA 诊断平台 — LLM API 中转配置

model_list:
  # ============================================================
  # 意图路由层（§5）— 快速、低成本
  # ============================================================
  - model_name: router-model
    litellm_params:
      model: anthropic/claude-haiku-4-5-20260301
      api_key: os.environ/ANTHROPIC_API_KEY
      max_tokens: 1024
    model_info:
      description: "意图路由 — Claude Haiku 主力"

  - model_name: router-model                    # 同名 = 自动负载均衡 + Fallback
    litellm_params:
      model: openai/gpt-5.4-nano
      api_key: os.environ/OPENAI_API_KEY
      max_tokens: 1024
    model_info:
      description: "意图路由 — OpenAI Fallback"

  # ============================================================
  # Agent 层（§8.1~8.3）— 长上下文 + Tool Use
  # Key Pool：同一模型挂多个 Key 实现轮转（§10 429 防御）
  # ============================================================
  - model_name: agent-model
    litellm_params:
      model: anthropic/claude-sonnet-4-6-20260301
      api_key: os.environ/ANTHROPIC_API_KEY_1
      rpm: 50                                    # 单 Key RPM 限制
      tpm: 400000                                # 单 Key TPM 限制
    model_info:
      description: "Agent — Claude Sonnet Key#1"

  - model_name: agent-model
    litellm_params:
      model: anthropic/claude-sonnet-4-6-20260301
      api_key: os.environ/ANTHROPIC_API_KEY_2
      rpm: 50
      tpm: 400000
    model_info:
      description: "Agent — Claude Sonnet Key#2"

  - model_name: agent-model
    litellm_params:
      model: openai/gpt-5.4-mini
      api_key: os.environ/OPENAI_API_KEY
      rpm: 500
      tpm: 2000000
    model_info:
      description: "Agent — OpenAI Fallback"

  # ============================================================
  # Synthesizer 层（§8.4）— 深度推理
  # ============================================================
  - model_name: synthesizer-model
    litellm_params:
      model: anthropic/claude-sonnet-4-6-20260301
      api_key: os.environ/ANTHROPIC_API_KEY_1
    model_info:
      description: "Synthesizer — Claude Sonnet 主力"

  - model_name: synthesizer-model
    litellm_params:
      model: openai/gpt-5.4
      api_key: os.environ/OPENAI_API_KEY
    model_info:
      description: "Synthesizer — OpenAI Fallback"

  # ============================================================
  # Embedding 层（§2 离线预处理）
  # ============================================================
  - model_name: embedding-model
    litellm_params:
      model: openai/text-embedding-3-large
      api_key: os.environ/OPENAI_API_KEY
    model_info:
      description: "Embedding — OpenAI text-embedding-3-large"

# ============================================================
# LiteLLM 全局设置
# ============================================================
litellm_settings:
  # 重试与 Fallback（对应方案 v6 §10 429 防御方案的前 4 层）
  num_retries: 3                                # 同一 deployment 重试次数
  request_timeout: 120                          # 单次请求超时

  # Fallback 链：同一 model_name 下的多个 deployment 自动 Fallback
  # Claude deployment 失败 → 自动切到同 model_name 下的 OpenAI deployment
  fallbacks:
    - {"router-model": ["router-model"]}
    - {"agent-model": ["agent-model"]}
    - {"synthesizer-model": ["synthesizer-model"]}

  allowed_fails: 3                              # 连续失败 3 次后临时移除该 deployment
  cooldown_time: 60                             # 移除后冷却 60 秒再重试

  # 日志
  success_callback: ["prometheus"]              # Prometheus 指标采集（可选）
  failure_callback: ["prometheus"]

# ============================================================
# 路由策略
# ============================================================
router_settings:
  routing_strategy: usage-based-routing         # 按使用量均衡分配到各 Key

# ============================================================
# 网关设置
# ============================================================
general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY     # 管理员 Key
```

> **说明**：原生部署时不需要 PostgreSQL 和 Redis。LiteLLM 的核心功能（Fallback、Key Pool 轮转、重试、负载均衡）**不依赖数据库**。仅 Virtual Key 管理和用量持久化需要 PostgreSQL，可在后续需要时再加。

### 5.4 环境变量文件

```bash
# /opt/litellm-proxy/.env（chmod 600，不入版本库）

# Anthropic API Keys（Key Pool，对应方案 v6 §10 Key Pool 轮转）
ANTHROPIC_API_KEY=sk-ant-api00-xxxxxxxxxxxxx
ANTHROPIC_API_KEY_1=sk-ant-api01-xxxxxxxxxxxxx
ANTHROPIC_API_KEY_2=sk-ant-api02-xxxxxxxxxxxxx

# OpenAI API Key
OPENAI_API_KEY=sk-xxxxxxxxxxxxx

# LiteLLM 管理密钥（用于调用 LiteLLM 管理接口和 Admin UI）
LITELLM_MASTER_KEY=sk-litellm-master-xxxxx
```

### 5.5 systemd 服务配置

```ini
# /etc/systemd/system/litellm.service
[Unit]
Description=LiteLLM Proxy - FOTA LLM API Gateway
After=network.target

[Service]
Type=exec
User=litellm
Group=litellm
WorkingDirectory=/opt/litellm-proxy

# 加载环境变量
EnvironmentFile=/opt/litellm-proxy/.env

# 启动命令
ExecStart=/opt/litellm-proxy/venv/bin/litellm \
    --config /opt/litellm-proxy/config.yaml \
    --host 127.0.0.1 \
    --port 4000 \
    --num_workers 4

# 日志输出到 journald（可用 journalctl -u litellm 查看）
StandardOutput=journal
StandardError=journal

# 自动重启
Restart=always
RestartSec=5

# 安全加固
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=/opt/litellm-proxy/logs

[Install]
WantedBy=multi-user.target
```

**启用并启动**：

```bash
sudo systemctl daemon-reload
sudo systemctl enable litellm
sudo systemctl start litellm

# 查看状态
sudo systemctl status litellm

# 查看日志（实时）
journalctl -u litellm -f

# 查看最近 100 行日志
journalctl -u litellm -n 100
```

### 5.6 Nginx 反向代理 + Cloudflare SSL

域名 DNS 托管在 Cloudflare，启用代理模式（橙色云朵）。Cloudflare 在边缘做 SSL 终止，服务器使用 Cloudflare Origin Certificate 加密回源链路。

**优势**（相比 Let's Encrypt）：
- 证书有效期 **15 年**，无需定时续签
- Cloudflare 边缘自动提供 DDoS 防护
- 隐藏服务器真实 IP

**配置步骤**：

```bash
# 1. 安装 Nginx
sudo apt install nginx

# 2. 在 Cloudflare Dashboard 生成 Origin Certificate：
#    SSL/TLS → Origin Server → Create Certificate
#    保存为以下两个文件：
sudo mkdir -p /etc/nginx/ssl
sudo nano /etc/nginx/ssl/origin-cert.pem     # 粘贴 Origin Certificate
sudo nano /etc/nginx/ssl/origin-key.pem      # 粘贴 Private Key
sudo chmod 600 /etc/nginx/ssl/origin-key.pem

# 3. Cloudflare SSL/TLS 模式设置为 Full (Strict)
```

```nginx
# /etc/nginx/sites-available/litellm
server {
    listen 443 ssl http2;
    server_name llm-proxy.example.com;

    # Cloudflare Origin Certificate（15 年有效，免续签）
    ssl_certificate     /etc/nginx/ssl/origin-cert.pem;
    ssl_certificate_key /etc/nginx/ssl/origin-key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    # 仅允许 Cloudflare IP 访问（防止绕过 CDN 直连源站）
    # Cloudflare IPv4: https://www.cloudflare.com/ips-v4
    allow 173.245.48.0/20;
    allow 103.21.244.0/22;
    allow 103.22.200.0/22;
    allow 103.31.4.0/22;
    allow 141.101.64.0/18;
    allow 108.162.192.0/18;
    allow 190.93.240.0/20;
    allow 188.114.96.0/20;
    allow 197.234.240.0/22;
    allow 198.41.128.0/17;
    allow 162.158.0.0/15;
    allow 104.16.0.0/13;
    allow 104.24.0.0/14;
    allow 172.64.0.0/13;
    allow 131.0.72.0/22;
    deny all;

    # 获取客户端真实 IP（Cloudflare 代理后）
    set_real_ip_from 173.245.48.0/20;
    set_real_ip_from 103.21.244.0/22;
    set_real_ip_from 103.22.200.0/22;
    set_real_ip_from 103.31.4.0/22;
    set_real_ip_from 141.101.64.0/18;
    set_real_ip_from 108.162.192.0/18;
    set_real_ip_from 190.93.240.0/20;
    set_real_ip_from 188.114.96.0/20;
    set_real_ip_from 197.234.240.0/22;
    set_real_ip_from 198.41.128.0/17;
    set_real_ip_from 162.158.0.0/15;
    set_real_ip_from 104.16.0.0/13;
    set_real_ip_from 104.24.0.0/14;
    set_real_ip_from 172.64.0.0/13;
    set_real_ip_from 131.0.72.0/22;
    real_ip_header CF-Connecting-IP;

    location / {
        proxy_pass http://127.0.0.1:4000;
        proxy_http_version 1.1;
        proxy_set_header Connection "";          # 长连接
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # Streaming SSE 支持（关键！）
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;                 # LLM 长输出超时
    }

    # LiteLLM Admin UI
    location /ui {
        proxy_pass http://127.0.0.1:4000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

# HTTP → HTTPS 重定向（Cloudflare 也会自动做，这里是双保险）
server {
    listen 80;
    server_name llm-proxy.example.com;
    return 301 https://$host$request_uri;
}
```

```bash
# 启用站点
sudo ln -s /etc/nginx/sites-available/litellm /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 5.7 快速验证（部署后立即测试）

```bash
# 1. 本机测试（SSH 到美国服务器上执行）
curl http://127.0.0.1:4000/health
# 预期: {"status": "healthy"}

# 2. 外部测试（从国内执行）
curl https://llm-proxy.example.com/health
# 预期: {"status": "healthy"}

# 3. 真实 LLM 调用测试
curl https://llm-proxy.example.com/v1/chat/completions \
  -H "Authorization: Bearer sk-litellm-master-xxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "router-model",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
# 预期: Claude Haiku 正常返回
```

### 5.8 运维命令速查

```bash
# 启动 / 停止 / 重启
sudo systemctl start litellm
sudo systemctl stop litellm
sudo systemctl restart litellm

# 查看运行状态
sudo systemctl status litellm

# 实时日志（调试利器）
journalctl -u litellm -f

# 修改配置后热重载
sudo systemctl restart litellm

# 升级 LiteLLM
sudo -u litellm /opt/litellm-proxy/venv/bin/pip install --upgrade 'litellm[proxy]'
sudo systemctl restart litellm
```

### 5.9 多台服务器高可用（可选）

利用现有的多台美国 CN2 GIA 服务器，可以部署多个 LiteLLM 实例做高可用：

```
                          ┌─ 服务器 A: LiteLLM :4000 ─→ Claude/OpenAI
中国大陆 → DNS 轮询/负载均衡 ┤
                          └─ 服务器 B: LiteLLM :4000 ─→ Claude/OpenAI
```

实现方式：
- **最简单**：DNS 轮询（A 记录指向两个 IP），FOTA 侧网络重试自动切换
- **自建**：选一台服务器部署 Nginx upstream 负载均衡（带 health_check，自动剔除故障节点）

每台服务器独立部署相同的 `config.yaml`，无状态，随时加减节点。

---

## 6. 两种场景对比总结

| 维度 | 场景 A：平台在国内 | 场景 B：开发在国内，生产在海外 |
|---|---|---|
| **生产环境 LLM 调用路径** | FOTA(国内) → LiteLLM(海外) → API | FOTA(海外) → 直连 API |
| **跨境请求** | 每次 LLM 调用都跨境 | 生产零跨境 |
| **方案 v6 LLMProvider 层** | 删除，替换为统一 openai SDK | 保留，直连模式 |
| **429 防御逻辑位置** | 迁移到 LiteLLM（海外） | 保留在 FOTA 代码内 |
| **LiteLLM 角色** | **生产核心组件** | **开发辅助工具** |
| **LiteLLM 挂了的影响** | 生产全挂 | 只影响开发调试 |
| **延迟** | +130~180ms（跨境） | 生产无额外延迟 |
| **日志数据合规** | 原始日志不出境 ✅（仅脱敏分析片段出境） | 原始日志及全量数据均存在海外 ⚠️ |
| **基础设施成本** | FOTA 服务器(国内) + 现有美国服务器 | 全部海外 + 现有美国服务器（仅开发） |
| **推荐指数** | ⭐⭐⭐⭐（合规友好） | ⭐⭐⭐⭐⭐（架构最简） |

---

## 7. 推荐落地路径

### 第 1 步：部署 LiteLLM（Day 1，30 分钟）

1. SSH 到一台美国 CN2 GIA 服务器
2. 按 §5.2 安装 LiteLLM（pip install）
3. 按 §5.3 写入 `config.yaml`，§5.4 写入 `.env`
4. 按 §5.5 创建 systemd 服务并启动
5. 按 §5.6 配置 Nginx + Cloudflare SSL
6. 按 §5.7 从国内执行验证命令

### 第 2 步：跑通核心调用验证（Day 1~2）

1. 验证 4 种调用模式：chat / tool_use / streaming / embedding
2. 验证 Fallback：故意用错 Claude Key，确认自动切到 OpenAI
3. 验证并发：asyncio.gather 同时发 3 个请求
4. 记录各链路延迟基线

### 第 3 步：FOTA 平台接入（Sprint 1）

1. 场景 A：FOTA 业务代码使用统一 `openai` SDK 调中转
2. 场景 B：实现 `create_llm_router()` 工厂函数，通过环境变量切换模式
3. 验证 Router / Agent / Synthesizer / Embedding 四种调用模式全部通路

### 第 4 步：生产加固（Sprint 2）

1. 可选：第二台美国服务器部署 LiteLLM，做 DNS 轮询高可用
2. 配置 Prometheus + Grafana 监控 LiteLLM 指标
3. 压测并发诊断场景（3 Agent 并行 × N 用户）
4. 根据实际用量调整 Key Pool 数量和 RPM/TPM 限制

---

## 8. 修订记录

| 版本 | 日期 | 修订内容 |
|---|---|---|
| v1 | 2026-04-01 | 初始版本。涵盖场景 A（平台在国内）和场景 B（开发在国内/生产在海外）两种部署方案；LiteLLM Proxy 完整部署配置；与方案 v6 §4/§10 的衔接改动说明。 |
