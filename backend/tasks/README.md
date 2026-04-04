# 任务队列使用指南

## 概述

本系统使用 **Arq** (基于Redis) 实现异步任务队列，用于处理耗时的日志解析任务。

## 架构

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   FastAPI   │─────▶│    Redis    │◀─────│ Arq Worker  │
│   (API)     │      │   (Queue)   │      │  (Process)  │
└─────────────┘      └─────────────┘      └─────────────┘
     提交任务            任务队列            执行任务
```

## 组件说明

### 1. 任务定义 (`tasks/worker.py`)

- **parse_logs_task**: 异步日志解析任务
  - 解析多个日志文件
  - 批量插入事件到数据库
  - 执行时间对齐
  - 支持失败重试

- **cleanup_old_tasks**: 定时清理任务（示例）

### 2. 任务客户端 (`tasks/client.py`)

- **TaskClient**: 任务提交和查询接口
  - `submit_parse_task()`: 提交解析任务
  - `get_task_status()`: 查询任务状态
  - `cancel_task()`: 取消任务
  - `get_queue_info()`: 获取队列信息

### 3. Worker配置 (`tasks/worker.py`)

```python
class WorkerSettings:
    redis_settings = RedisSettings(host="localhost", port=6379)
    max_jobs = 10              # 最大并发任务数
    job_timeout = 3600         # 任务超时时间（秒）
    keep_result = 86400        # 保留任务结果时间（秒）
    max_tries = 3              # 最大重试次数
```

## 使用方法

### 启动Worker

#### 方法1: 使用Python脚本

```bash
cd backend
python run_worker.py
```

#### 方法2: 使用arq命令

```bash
cd backend
arq tasks.worker.WorkerSettings
```

#### 方法3: 使用systemd服务（生产环境）

```bash
# 创建systemd服务文件
sudo nano /etc/systemd/system/fota-worker.service
```

```ini
[Unit]
Description=FOTA Arq Worker
After=network.target redis.service postgresql.service

[Service]
Type=simple
User=fota
WorkingDirectory=/opt/fota/backend
Environment="PATH=/opt/fota/venv/bin"
ExecStart=/opt/fota/venv/bin/python run_worker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# 启动服务
sudo systemctl daemon-reload
sudo systemctl enable fota-worker
sudo systemctl start fota-worker

# 查看状态
sudo systemctl status fota-worker

# 查看日志
sudo journalctl -u fota-worker -f
```

### API使用示例

#### 1. 提交解析任务

```bash
curl -X POST "http://localhost:8000/api/parse/submit" \
  -H "Content-Type: application/json" \
  -d '{
    "case_id": "case_001",
    "file_ids": ["file_001", "file_002"],
    "time_window_start": "2024-01-01T00:00:00",
    "time_window_end": "2024-01-01T23:59:59",
    "max_lines_per_file": 100000
  }'
```

响应:
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "case_id": "case_001",
  "status": "pending",
  "total_files": 2,
  "parsed_files": 0,
  "failed_files": 0,
  "total_events": 0,
  "created_at": "2024-01-01T10:00:00",
  "updated_at": "2024-01-01T10:00:00"
}
```

#### 2. 查询任务状态

```bash
curl "http://localhost:8000/api/parse/status/550e8400-e29b-41d4-a716-446655440000"
```

响应（进行中）:
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "enqueue_time": "2024-01-01T10:00:00",
  "start_time": "2024-01-01T10:00:05",
  "finish_time": null
}
```

响应（已完成）:
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "enqueue_time": "2024-01-01T10:00:00",
  "start_time": "2024-01-01T10:00:05",
  "finish_time": "2024-01-01T10:05:30",
  "result": {
    "case_id": "case_001",
    "total_files": 2,
    "parsed_files": 2,
    "failed_files": 0,
    "total_events": 15234,
    "status": "completed"
  }
}
```

## 任务状态说明

| 状态 | 说明 |
|------|------|
| `pending` | 任务已提交，等待执行 |
| `running` | 任务正在执行中 |
| `completed` | 任务执行成功 |
| `failed` | 任务执行失败 |
| `not_found` | 任务不存在或已过期 |

## 监控和调试

### 查看Redis队列

```bash
# 连接Redis
redis-cli

# 查看队列长度
ZCARD arq:queue

# 查看队列中的任务
ZRANGE arq:queue 0 -1 WITHSCORES

# 查看任务详情
GET arq:result:{task_id}
```

### Worker日志

Worker会输出详细的日志信息：

```
2024-01-01 10:00:05 - tasks.worker - INFO - 开始解析任务 - Case: case_001, Files: 2
2024-01-01 10:00:10 - tasks.worker - INFO - 文件解析完成: file_001, 事件数: 7500
2024-01-01 10:00:15 - tasks.worker - INFO - 文件解析完成: file_002, 事件数: 7734
2024-01-01 10:00:20 - tasks.worker - INFO - 开始时间对齐 - Case: case_001
2024-01-01 10:00:25 - tasks.worker - INFO - 时间对齐完成 - Case: case_001, 状态: ALIGNED
2024-01-01 10:00:30 - tasks.worker - INFO - 解析任务完成 - {...}
```

## 性能优化

### 1. 调整并发数

根据服务器资源调整 `max_jobs`:

```python
# tasks/worker.py
class WorkerSettings:
    max_jobs = 20  # 增加并发数
```

### 2. 多Worker实例

启动多个Worker进程以提高吞吐量:

```bash
# 启动3个Worker实例
python run_worker.py &
python run_worker.py &
python run_worker.py &
```

### 3. 批量大小优化

调整批量插入大小:

```python
# 在parse_logs_task中
inserted_count = BatchOperations.bulk_insert_events(db, event_dicts, batch_size=2000)
```

## 故障排查

### 问题1: Worker无法连接Redis

**症状**: Worker启动失败，提示连接错误

**解决**:
```bash
# 检查Redis是否运行
sudo systemctl status redis

# 检查Redis配置
redis-cli ping

# 检查环境变量
echo $REDIS_HOST
echo $REDIS_PORT
```

### 问题2: 任务一直处于pending状态

**症状**: 任务提交后长时间不执行

**解决**:
1. 检查Worker是否运行
2. 查看Worker日志是否有错误
3. 检查Redis队列是否堵塞

### 问题3: 任务执行失败

**症状**: 任务状态变为failed

**解决**:
1. 查看任务结果中的error字段
2. 检查Worker日志
3. 验证数据库连接
4. 检查文件路径是否正确

## 最佳实践

1. **生产环境使用systemd管理Worker**
2. **配置合理的超时时间**（根据文件大小）
3. **启用失败重试**（已默认启用，最多3次）
4. **定期清理过期任务结果**
5. **监控队列长度**，防止积压
6. **使用Redis持久化**，防止任务丢失

## 相关文档

- [Arq官方文档](https://arq-docs.helpmanual.io/)
- [Redis文档](https://redis.io/documentation)
- [FastAPI后台任务](https://fastapi.tiangolo.com/tutorial/background-tasks/)
