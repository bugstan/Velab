# FOTA 智能诊断平台 - Backend API

FOTA 多域日志智能诊断系统的后端服务，基于 FastAPI 构建，提供多智能体协同诊断能力 + 自带的整车日志摄取管线（log_pipeline）。

---

## 📋 目录结构

```
backend/
├── main.py                       # FastAPI 应用入口（生命周期初始化 db_manager / task client / log_pipeline state）
├── config.py                     # 平台级统一配置（PG / Redis / LLM / 部署模式）
├── database.py                   # PostgreSQL 连接管理（仅供 cases / confirmed_diagnosis 使用）
├── requirements.txt
├── .env.example
├── run_worker.py                 # Arq Worker 启动脚本
├── data/                         # log_pipeline 默认数据根（bundles / catalog.db / indexes / uploads / work）
│
├── agents/                       # 多 Agent 实现（自动注册到 registry）
│   ├── base.py
│   ├── orchestrator.py
│   ├── log_analytics.py
│   ├── jira_knowledge.py
│   ├── doc_retrieval.py
│   └── rca_synthesizer.py
│
├── api/                          # 平台业务 API（cases / feedback）+ 转发 log_pipeline 的 bundles router
│   ├── __init__.py               # 路由组装：cases + feedback + log_pipeline.bundles_router
│   ├── schemas.py                # 仅保留 Case + 通用响应 schema
│   ├── cases.py                  # 案例 CRUD
│   └── feedback.py               # 已确认诊断 + 反馈闭环
│
├── log_pipeline/                 # 整车日志摄取管线（独立子系统，详见 log_pipeline/CLAUDE.md）
│   ├── CLAUDE.md                 # 模块设计契约（必读）
│   ├── config.py                 # Settings.from_env() — 数据/配置路径解析
│   ├── interfaces.py             # 数据模型与 Protocol
│   ├── ingest/                   # 解压 / 分类 / 落盘 + IngestPipeline 编排
│   ├── decoders/                 # DLT / Android / Kernel / MCU / TBOX / iBDU / FOTA
│   ├── prescan/                  # 单遍扫描：事件 + 锚点 + 5min 桶索引 + unsynced 区段
│   ├── alignment/                # 直接对齐 + 两跳对齐 + 30 天合理性校验
│   ├── storage/                  # SQLite catalog / eventdb / 文件存储
│   ├── query/                    # 时间窗口查询 + slim 三级过滤
│   ├── api/http.py               # FastAPI APIRouter + Prometheus /metrics + create_app（独立 app）
│   ├── config/                   # 外置规则 YAML（controllers / event_rules / anchor_rules / slim_rules）
│   └── tests/                    # 101 项独立测试（自带 conftest）
│
├── models/                       # 平台业务 ORM（PG）
│   ├── base.py
│   ├── case.py                   # Case
│   └── diagnosis.py              # ConfirmedDiagnosis
│
├── services/                     # 服务层（不含日志解析；日志解析全部走 log_pipeline）
│   ├── llm.py
│   ├── vector_search.py
│   ├── semantic_cache.py
│   ├── tool_functions.py         # Agent Tool Use（workspace 读写）
│   ├── workspace_manager.py      # Agent Markdown 工作区沙盒
│   ├── doc_chunker.py
│   └── evaluation.py
│
├── tasks/                        # Arq 异步任务（薄包装 IngestPipeline）
│   ├── __init__.py
│   ├── worker.py                 # parse_bundle_task → IngestPipeline.run（进度 1s 轮询写 Redis）
│   ├── client.py                 # TaskClient（submit_bundle_task / get_task_status / cancel_task）
│   └── README.md                 # 任务队列使用文档
│
├── tests/                        # 平台业务侧测试（cases / feedback / workspace_manager）
│   ├── conftest.py               # SQLite 内存 PG 替身 + Case fixture
│   ├── test_workspace_manager.py
│   └── README.md
│
├── common/                       # 公共模块
│   ├── chain_log.py
│   └── redaction.py
│
├── scripts/                      # 部署 + 启动
├── systemd/
└── nginx/
```

---

## 🧩 系统组成

后端可以拆成两个相对独立的子系统：

### 1. 平台业务层（FastAPI + PG + Agents）

- 路由：`/chat`（SSE）、`/api/cases`、`/api/feedback`
- 持久化：PostgreSQL，仅 `cases` + `confirmed_diagnosis` 两张表
- 核心：多 Agent 编排（log_analytics + jira_knowledge + doc_retrieval + rca_synthesizer）

### 2. log_pipeline 子系统（独立可测）

- 路由：`/api/bundles`（上传）、`/api/bundles/{id}`、`/api/bundles/{id}/logs`、`/api/bundles/{id}/events`、`/metrics`
- 持久化：**SQLite** `data/catalog.db`（bundle / file 元数据 + ImportantEvent），日志原文落磁盘绝不入库
- 入口：`IngestPipeline.register_upload(...) → IngestPipeline.run(bundle_id, archive)`
- 详细契约见 [`log_pipeline/CLAUDE.md`](log_pipeline/CLAUDE.md)

两个子系统通过 `backend/api/__init__.py` 拼成同一个 FastAPI app；`main.py` 的 lifespan 负责依次初始化 PG 连接池、Arq 任务客户端、log_pipeline state。

---

## 🚀 快速启动（开发环境）

### 1. 安装依赖
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env：DATABASE_URL / REDIS_HOST / LLM_API_KEYS / DEPLOYMENT_MODE
```

### 3. 启动服务
```bash
./scripts/start-dev.sh        # 推荐：同时拉起 backend + worker
# 或仅启动 API：
python main.py
# Arq Worker（在另一个终端）：
python run_worker.py
```

### 4. 验证
```bash
curl http://localhost:8000/health                # → {"status":"ok","agents":[...]}
curl http://localhost:8000/metrics               # → Prometheus 文本
open  http://localhost:8000/docs                 # Swagger UI
```

### 5. 上传一个 bundle 测一下
```bash
curl -F "file=@/path/to/bundle.zip" http://localhost:8000/api/bundles
# → {"bundle_id":"...","status":"queued"}

curl http://localhost:8000/api/bundles/{bundle_id}
# → {"status":"prescanning","progress":0.72,"file_count":42,...}
```

---

## 🏭 生产环境部署

### 前置准备
1. **服务器要求**：Linux（Ubuntu 22.04 / Debian 12）、Python ≥ 3.10、内存 ≥ 4GB、磁盘 ≥ 50GB
2. **依赖服务**：PostgreSQL ≥ 14（pgvector）、Redis ≥ 6.0
3. **存储路径**：log_pipeline 默认写 `backend/data/`；生产建议改 `LOG_PIPELINE_DATA_ROOT=/var/lib/fota/data`

### 自动化部署
```bash
git clone <repository-url>
cd Velab/backend
sudo ./scripts/deploy.sh
```
脚本完成：用户 `fota` / 部署目录 `/opt/fota-backend` / Python venv / 依赖安装 / systemd 服务 / 文件权限。

### 手动部署关键步骤

```bash
# 1. 创建用户与目录
sudo useradd -r -s /sbin/nologin -d /opt/fota-backend fota
sudo mkdir -p /opt/fota-backend/{logs,data}

# 2. 部署代码 + 配置
sudo cp -r . /opt/fota-backend/
sudo chown -R fota:fota /opt/fota-backend
sudo cp .env.example /opt/fota-backend/.env
sudo chmod 600 /opt/fota-backend/.env

# 3. Python 环境
cd /opt/fota-backend
sudo -u fota python3 -m venv venv
sudo -u fota venv/bin/pip install -r requirements.txt

# 4. systemd 服务
sudo cp systemd/fota-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fota-backend

# 5. Worker（独立 service，配置见 tasks/README.md）
sudo systemctl enable --now fota-worker

# 6. Nginx 反向代理
sudo cp nginx/backend.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/backend.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

---

## 🔧 运维命令速查

```bash
# 服务生命周期
sudo systemctl {start|stop|restart|status} fota-backend
sudo systemctl {start|stop|restart|status} fota-worker

# 日志
journalctl -u fota-backend -f
journalctl -u fota-worker  -f
tail -f /opt/fota-backend/logs/app.log

# 更新部署
cd /opt/fota-backend && sudo -u fota git pull
sudo -u fota venv/bin/pip install -r requirements.txt
sudo systemctl restart fota-backend fota-worker
```

---

## 📊 监控与日志

```bash
# 健康检查
curl http://localhost:8000/health

# log_pipeline Prometheus 指标
curl http://localhost:8000/metrics
# 内置：log_pipeline_bundles_total / files_total / events_extracted_total / alignment_offset_seconds / alignment_confidence

# 实时业务日志
journalctl -u fota-backend -f
journalctl -u fota-backend --since "2026-04-30 10:00:00" -p err
```

---

## 🧪 测试

```bash
# 全量
python -m pytest log_pipeline/tests/ tests/ -q

# 仅 log_pipeline 子系统（独立 conftest，不需要 PG）
python -m pytest log_pipeline/tests/ -q

# 仅平台业务
python -m pytest tests/ -q
```

---

## 🔐 安全实践

1. `.env` 权限 600，不入库
2. Backend 监听 127.0.0.1，对外走 Nginx + HTTPS
3. systemd 用专用用户 `fota` + 安全加固
4. 日志走 `common/redaction.py`，VIN / 手机号等敏感字段在 API 出口脱敏

---

## 🚨 故障排查

### 服务起不来
```bash
journalctl -u fota-backend -n 50
# 常见：.env 缺失 / PG 连接失败 / 端口 8000 被占 / 依赖缺失
```

### bundle 上传后一直 queued
```bash
# Worker 没起来或 Redis 不通
sudo systemctl status fota-worker
redis-cli ping
journalctl -u fota-worker -f
```

### 查询 /api/bundles/{id} 返回 BUNDLE_NOT_FOUND
```bash
# 检查 SQLite catalog 是否生成
ls -lh /opt/fota-backend/data/catalog.db
# 或自定义路径下
ls -lh "${LOG_PIPELINE_DATA_ROOT:-/opt/fota-backend/data}/catalog.db"
```

### LLM API 失败
```bash
journalctl -u fota-backend -f
# 检查 DEPLOYMENT_MODE / Gateway 是否在 / API Key 是否有效
```

### Nginx 502
```bash
sudo systemctl status fota-backend
sudo netstat -tlnp | grep 8000
sudo tail -f /var/log/nginx/fota-backend-error.log
```

---

## 🔗 相关文档

- [`log_pipeline/CLAUDE.md`](log_pipeline/CLAUDE.md) — 日志摄取管线设计契约（接口/存储/对齐算法）
- [`tasks/README.md`](tasks/README.md) — Arq 任务队列使用
- [`../docs/`](../docs/) — 整体架构与可行性文档

---

## 📝 核心特性

- ✅ **多智能体协同**：log_analytics + jira_knowledge + doc_retrieval + rca_synthesizer 三路证据融合
- ✅ **整车日志摄取**：解压 → 分类 → 解码 → 单遍预扫 → 时间对齐 → 持久化（≤ 3 min / 2 GB bundle）
- ✅ **不写回时间戳**：所有 `aligned_ts = raw_ts + offset` 查询时即时计算
- ✅ **日志行不入库**：保留磁盘文件 + 5min 桶索引；只把重要事件入 SQLite EventDB
- ✅ **双供应商 Fallback**：Claude 主力 + OpenAI 备用，含 429 限流防御
- ✅ **语义缓存**：预估 50~70% 缓存命中率
- ✅ **防幻觉护栏**：引用 ID 断言验证 + 置信度量化
- ✅ **可追溯证据链**：每条结论可回溯到原始日志行号

---

## 🏗️ 架构说明

### 部署模式

通过 `DEPLOYMENT_MODE` 环境变量切换：

**场景 A**（平台在国内）
```
Backend (中国) → LiteLLM Gateway (美国) → Claude / OpenAI
```

**场景 B**（平台在海外）
```
Backend (海外) → 直连 Claude / OpenAI
```

### 技术栈

- **Web**：FastAPI（async/await）+ SSE
- **任务队列**：Arq（async-native）
- **日志摄取**：自研 log_pipeline（流式 + ProcessPoolExecutor 并行预扫）
- **业务持久化**：PostgreSQL + pgvector
- **日志元数据**：SQLite（log_pipeline 自管，与 PG 隔离）
- **缓存**：Redis（含 Arq job + task progress）
- **LLM**：统一抽象层（Claude + OpenAI），prompt cache + 语义 cache 双层
