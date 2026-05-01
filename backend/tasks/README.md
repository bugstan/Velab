# 任务队列使用指南

## 概述

本系统使用 **Arq**（基于 Redis）实现异步任务队列。当前唯一的业务任务是 `parse_bundle_task` —— 它是 [`log_pipeline.IngestPipeline`](../log_pipeline/CLAUDE.md) 的薄包装，负责接管整车日志压缩包的全链路摄取（解压 → 分类 → 解码 → 单遍预扫描 → 时间对齐 → 持久化）。

进度（status / progress 0–1）由 Worker 后台任务**每 1 秒**从 SQLite catalog 中读取并写入 Redis 键 `task_progress:{task_id}`，前端按 `bundle_id` 直接轮询 `/api/bundles/{id}` 即可拿到 `progress`、`status`、`files_by_controller` 等结构化字段（不再依赖 `task_id`）。

## 架构

```
┌──────────────┐  POST /api/bundles  ┌──────────────┐  enqueue   ┌──────────────┐
│   Frontend   │ ──────────────────▶ │  FastAPI app │ ─────────▶ │    Redis     │
└──────────────┘                     └──────────────┘            │  (Arq queue) │
        │                                    │                   └──────┬───────┘
        │ poll /api/bundles/{id}             │ background_tasks         │
        │       (every 1s)                   ▼                          │ pop
        │                            ┌──────────────┐         ┌────────▼────────┐
        └──────────────────────────▶ │ SQLite       │◀────────│   Arq Worker    │
                                     │ catalog.db   │  write  │  parse_bundle_  │
                                     │ (progress,   │  status │  task           │
                                     │  events,     │         │  → IngestPipeline│
                                     │  meta)       │         └─────────────────┘
                                     └──────────────┘
```

> 注：FastAPI app 在 `BackgroundTasks` 中也会直接跑同一份 `IngestPipeline.run` —— 这是 log_pipeline 自己的 `/api/bundles` 路由提供的同步路径（用于无 Arq 部署）。生产环境推荐用 Arq Worker，避免阻塞 HTTP 进程。

## 组件

### `tasks/worker.py`

| 名字 | 作用 |
|---|---|
| `parse_bundle_task(ctx, case_id, upload_path, upload_name)` | Arq 任务函数。`asyncio.to_thread(pipeline.run, ...)` 跑解析；并行起一个 `_poll_progress()` task 把 catalog 中的进度写回 Redis |
| `WorkerSettings` | Arq Worker 配置：Redis 连接、`functions=[parse_bundle_task]`、`max_jobs=10`、`job_timeout=3600`、`max_tries=3` |
| `cleanup_old_tasks` | 占位定时任务（cron 每天 02:00） |

### `tasks/client.py`

| 方法 | 作用 |
|---|---|
| `submit_bundle_task(case_id, upload_path, upload_name) → task_id` | 入队 + 写初始 `task_progress:{task_id}={percent:5, stage:"queued"}` |
| `get_task_status(task_id)` | 读 Arq job 状态 + Redis 中的 progress；返回 `{task_id, status, enqueue_time, start_time, finish_time, progress, result?, error?}` |
| `cancel_task(task_id)` | `Job(task_id).abort()` |
| `get_queue_info()` | `ZCARD arq:queue` 等队列统计 |

> ⚠️ Frontend 现在统一走 `/api/bundles/{bundle_id}` 拉状态，不再用 `get_task_status` —— 后者保留是为了排查/管理用途。`bundle_id`（log_pipeline 分配的 UUID）和 Arq `task_id` 是两个独立 ID，可通过 `parse_bundle_task` 的返回值 `result.bundle_id` 关联。

## 使用方法

### 启动 Worker

```bash
# 方式 1：启动脚本
cd backend && python run_worker.py

# 方式 2：arq CLI
cd backend && arq tasks.worker.WorkerSettings

# 方式 3：systemd（生产）
sudo nano /etc/systemd/system/fota-worker.service
```

```ini
[Unit]
Description=FOTA Arq Worker
After=network.target redis.service postgresql.service

[Service]
Type=simple
User=fota
WorkingDirectory=/opt/fota-backend
Environment="PATH=/opt/fota-backend/venv/bin"
Environment="LOG_PIPELINE_DATA_ROOT=/var/lib/fota/data"
ExecStart=/opt/fota-backend/venv/bin/python run_worker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now fota-worker
sudo systemctl status fota-worker
sudo journalctl -u fota-worker -f
```

### API 调用示例

#### 1. 上传 bundle（提交 Arq 任务）

通过 `/api/bundles` 上传时，FastAPI 会**直接同步起一个 BackgroundTask** 调用 `IngestPipeline`，不走 Arq。要走 Arq 队列，前端调用 `/api/upload-log`，由 Web 中转层走 `task_client.submit_bundle_task` 入队。

```bash
curl -F "file=@/path/to/bundle.zip" http://localhost:8000/api/bundles
# → {"bundle_id": "550e8400-e29b-41d4-a716-446655440000", "status": "queued"}
```

#### 2. 查询进度（前端推荐路径 —— 直接读 catalog）

```bash
curl http://localhost:8000/api/bundles/550e8400-e29b-41d4-a716-446655440000
```

```json
{
  "bundle_id": "550e8400-...",
  "status": "prescanning",
  "progress": 0.83,
  "archive_filename": "20260430_demo.zip",
  "archive_size_bytes": 1342177280,
  "error": null,
  "file_count": 142,
  "files_by_controller": {"android": 98, "tbox": 12, "mcu": 18, "kernel": 8, "ibdu": 6}
}
```

#### 3. 任务级状态（Arq 视角，运维用）

```bash
# 不直接暴露 HTTP；通过 Python REPL：
python -c "
import asyncio
from tasks.client import get_task_client
async def main():
    tc = await get_task_client()
    print(await tc.get_task_status('arq-job-id-xxx'))
asyncio.run(main())
"
```

## 状态映射

`/api/bundles/{id}.status` 直接来自 log_pipeline 的 `BundleStatus` 枚举，按阶段递进：

| status | 进度区间（progress） | 说明 |
|---|---|---|
| `queued` | 0.05 | 任务已入队，待执行 |
| `extracting` | 0.05 → 0.4 | 解压 + 分类 + 落盘 |
| `decoding` | 0.4 → 0.7 | DLT/文本 解码（细粒度刷新，每 1% 写一次） |
| `prescanning` | 0.7 → 0.9 | 单遍扫描：事件 + 锚点 + 桶索引（细粒度刷新） |
| `aligning` | 0.9 → 1.0 | 时间对齐 + 异常检测 |
| `done` | 1.0 | 全部完成 |
| `failed` | （任意点） | 见 `error` 字段 |

Arq 任务的状态映射（`get_task_status`）：

| Arq | client.py 输出 |
|---|---|
| `queued / deferred` | `pending` |
| `in_progress` | `running` |
| `complete` | `completed` |
| `not_found` | `not_found` |

## 监控 / 调试

### 查 Redis 队列

```bash
redis-cli ZCARD arq:queue                                    # 队列长度
redis-cli ZRANGE arq:queue 0 -1 WITHSCORES                   # 待执行任务
redis-cli GET task_progress:<task_id>                        # 当前进度（JSON 字符串）
redis-cli GET arq:result:<task_id>                           # 最终结果（pickled）
```

### Worker 日志样例

```
2026-04-30 10:00:05  INFO  ingest_pipeline  upload archive='demo.zip' size=1342177280
2026-04-30 10:00:05  INFO  ingest_pipeline  extract+classify+store START
2026-04-30 10:01:20  INFO  ingest_pipeline  decode counts={'DLTDecoder': 12, 'AndroidLogcatDecoder': 98, ...}
2026-04-30 10:02:45  INFO  ingest_pipeline  prescan events=15234 anchors=412 indexed_files=132 unsynced_files=4 workers=8
2026-04-30 10:03:10  INFO  ingest_pipeline  alignment direct=4 two_hop=2 fallback=0 status=success
2026-04-30 10:03:11  INFO  tasks.worker     bundle done bundle_id=550e8400-... case=demo_case
```

## 性能优化

### 1. 调整并发任务数

```python
# tasks/worker.py
class WorkerSettings:
    max_jobs = 20          # 默认 10
```

### 2. 多 Worker 实例

```bash
# 横向扩展，共享同一个 Redis 队列；每个 Worker 仍独立访问 SQLite catalog（WAL 模式可并发读，写仍需序列化）
python run_worker.py &
python run_worker.py &
python run_worker.py &
```

> ⚠️ 多 Worker 同时写同一个 `catalog.db` 会因 SQLite 单写锁串行化。生产建议：要么单 Worker + 单 SQLite，要么按 bundle 分片到多 SQLite（每分片一个 catalog）。

### 3. 单 bundle 内的并行度

预扫描阶段已用 `ProcessPoolExecutor`（fork ctx）按文件并发，worker 数 = `os.cpu_count()`。无需在任务层再加并行。

## 故障排查

### 1. Worker 无法连接 Redis
```bash
sudo systemctl status redis
redis-cli ping                                  # 应返回 PONG
echo $REDIS_HOST $REDIS_PORT
```

### 2. 任务一直 `queued`
- Worker 没启 → `sudo systemctl status fota-worker`
- Redis 不通 → `redis-cli ping`
- Worker 日志看错误 → `journalctl -u fota-worker -n 100`

### 3. 任务执行失败（`failed`）
- 看 `result.error` 字段
- 查 SQLite catalog：`sqlite3 data/catalog.db "SELECT bundle_id,status,error FROM bundles ORDER BY updated_at DESC LIMIT 5"`
- 查 bundle 处理日志：`cat data/bundles/{bundle_id}/_processing.log`

### 4. 进度长时间不动
- catalog 卡在某阶段 → 看 `_processing.log` 的 stage 时间戳
- decode 阶段慢 → 检查 DLT 文件大小 + decoder 吞吐
- prescan 阶段慢 → 检查 worker 数与 CPU 使用率

### 5. SQLite "database is locked"
- 多 Worker 并发写同一个 catalog → 串行化 / 分片
- 检查是否有外部进程在持有数据库连接（`fuser data/catalog.db`）

## 最佳实践

1. **生产环境用 systemd 管理 Worker**，配置 `Restart=always`
2. **`job_timeout` 按最大 bundle 设置**：默认 3600s（1h）足够 2 GB bundle
3. **`max_tries=3` + 失败重试默认开启** —— log_pipeline 是幂等的，重跑安全（但会复用旧 bundle_id 还是新分配，取决于上层入参；当前是新分配）
4. **`task_progress:{id}` 设了 1h TTL**，超时后前端只能查 `/api/bundles/{id}` 拿状态（catalog 永久保留）
5. **监控队列长度**：`ZCARD arq:queue` > 50 时考虑加 Worker
6. **Redis 持久化打开**（AOF / RDB），防止任务丢失
7. **大 bundle 上传走 Arq，小 bundle 直接走 BackgroundTasks**（HTTP 同步快，不占队列槽位）

## 相关文档

- [`../log_pipeline/CLAUDE.md`](../log_pipeline/CLAUDE.md) — 摄取管线设计契约（必读）
- [Arq 官方文档](https://arq-docs.helpmanual.io/)
- [Redis 文档](https://redis.io/documentation)
- [FastAPI 后台任务](https://fastapi.tiangolo.com/tutorial/background-tasks/)
