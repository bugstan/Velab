# FOTA 智能诊断平台 - Backend API

FOTA 多域日志智能诊断系统的后端服务，基于 FastAPI 构建，提供多智能体协同诊断能力。

---

## 📋 目录结构

```
backend/
├── main.py                  # FastAPI 应用入口
├── config.py                # 统一配置管理
├── requirements.txt         # Python 依赖
├── .env.example             # 环境变量配置示例
├── agents/                  # Agent 实现
│   ├── base.py              # Agent 基类和注册机制
│   ├── orchestrator.py      # 编排器
│   ├── log_analytics.py     # 日志分析 Agent
│   └── jira_knowledge.py    # Jira 知识库 Agent
├── services/                # 服务层
│   ├── llm.py               # LLM 服务抽象
│   └── __init__.py
├── common/                  # 公共模块
│   └── chain_log.py         # 结构化日志
├── scripts/                 # 部署和启动脚本
│   ├── deploy.sh            # 生产环境部署脚本
│   └── start-dev.sh         # 开发环境启动脚本
├── systemd/                 # systemd 服务配置
│   └── fota-backend.service
└── nginx/                   # Nginx 反向代理配置
    └── backend.conf
```

---

## 🚀 快速启动（开发环境）

### 1. 安装依赖

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入真实配置
```

### 3. 启动服务

**方式 A：使用启动脚本（推荐）**
```bash
chmod +x scripts/start-dev.sh
./scripts/start-dev.sh
```

**方式 B：直接运行**
```bash
python main.py
```

### 4. 验证服务

```bash
# 健康检查
curl http://localhost:8000/health

# API 文档
open http://localhost:8000/docs
```

---

## 🏭 生产环境部署

### 前置准备

1. **服务器要求**
   - 操作系统：Linux（推荐 Ubuntu 22.04 / Debian 12）
   - Python：≥ 3.10
   - 内存：≥ 4GB
   - 磁盘：≥ 50GB

2. **依赖服务**
   - PostgreSQL ≥ 14（含 pgvector 扩展）
   - Redis ≥ 6.0
   - MinIO 或 S3 兼容对象存储

### 自动化部署（推荐）

```bash
# 克隆代码到服务器
git clone <repository-url>
cd Velab/backend

# 运行部署脚本
sudo chmod +x scripts/deploy.sh
sudo ./scripts/deploy.sh
```

部署脚本会自动完成：
- ✅ 创建系统用户 `fota`
- ✅ 创建部署目录 `/opt/fota-backend`
- ✅ 配置 Python 虚拟环境
- ✅ 安装依赖
- ✅ 配置 systemd 服务
- ✅ 设置文件权限

### 手动部署步骤

#### 步骤 1：创建系统用户

```bash
sudo useradd -r -s /sbin/nologin -d /opt/fota-backend fota
sudo mkdir -p /opt/fota-backend/{logs,data}
```

#### 步骤 2：部署代码

```bash
sudo cp -r . /opt/fota-backend/
sudo chown -R fota:fota /opt/fota-backend
```

#### 步骤 3：配置 Python 环境

```bash
cd /opt/fota-backend
sudo -u fota python3 -m venv venv
sudo -u fota venv/bin/pip install -r requirements.txt
```

#### 步骤 4：配置环境变量

```bash
sudo cp .env.example .env
sudo nano .env  # 填入真实配置
sudo chmod 600 .env
sudo chown fota:fota .env
```

#### 步骤 5：配置 systemd 服务

```bash
sudo cp systemd/fota-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable fota-backend
sudo systemctl start fota-backend
```

#### 步骤 6：配置 Nginx 反向代理

```bash
# 安装 Nginx
sudo apt install nginx

# 复制配置文件
sudo cp nginx/backend.conf /etc/nginx/sites-available/

# 修改域名（替换 fota-api.example.com 为你的域名）
sudo nano /etc/nginx/sites-available/backend.conf

# 启用站点
sudo ln -s /etc/nginx/sites-available/backend.conf /etc/nginx/sites-enabled/

# 测试配置
sudo nginx -t

# 重载 Nginx
sudo systemctl reload nginx
```

---

## 🔧 运维命令速查

### systemd 服务管理

```bash
# 启动 / 停止 / 重启
sudo systemctl start fota-backend
sudo systemctl stop fota-backend
sudo systemctl restart fota-backend

# 查看运行状态
sudo systemctl status fota-backend

# 实时日志
journalctl -u fota-backend -f

# 查看最近 100 行日志
journalctl -u fota-backend -n 100
```

### 应用管理

```bash
# 更新代码
cd /opt/fota-backend
sudo -u fota git pull
sudo systemctl restart fota-backend

# 更新依赖
sudo -u fota /opt/fota-backend/venv/bin/pip install -r requirements.txt
sudo systemctl restart fota-backend

# 查看应用日志
tail -f /opt/fota-backend/logs/app.log
```

---

## 📊 监控与日志

### 查看应用日志

```bash
# 实时日志
journalctl -u fota-backend -f

# 按时间范围查询
journalctl -u fota-backend --since "2026-04-02 10:00:00" --until "2026-04-02 11:00:00"

# 只看错误日志
journalctl -u fota-backend -p err
```

### 健康检查

```bash
# 本地检查
curl http://localhost:8000/health

# 外部检查（通过 Nginx）
curl https://fota-api.example.com/health
```

### 性能监控

```bash
# 查看进程资源占用
ps aux | grep uvicorn

# 查看端口监听
sudo netstat -tlnp | grep 8000

# 查看连接数
sudo netstat -an | grep 8000 | wc -l
```

---

## 🔐 安全最佳实践

1. **环境变量保护**
   - `.env` 文件权限设置为 `600`
   - 不要提交 `.env` 到版本库
   - 定期轮换 API Keys

2. **网络安全**
   - Backend 只监听 `127.0.0.1`（通过 Nginx 对外）
   - 配置防火墙规则
   - 使用 HTTPS（Let's Encrypt 或 Cloudflare SSL）

3. **服务隔离**
   - Backend 运行在专用用户 `fota` 下
   - systemd 配置了安全加固选项
   - 限制文件系统访问权限

4. **日志审计**
   - 所有 API 请求记录在 Nginx access log
   - journald 保留 systemd 服务日志
   - 结构化日志便于分析

---

## 🚨 故障排查

### 问题 1：服务无法启动

```bash
# 查看详细错误
journalctl -u fota-backend -n 50

# 常见原因：
# - .env 文件缺失或格式错误
# - 数据库连接失败
# - 端口 8000 被占用
# - Python 依赖缺失
```

### 问题 2：数据库连接失败

```bash
# 检查 PostgreSQL 服务
sudo systemctl status postgresql

# 测试数据库连接
psql -h localhost -U postgres -d fota_db

# 检查 .env 中的数据库配置
cat /opt/fota-backend/.env | grep POSTGRES
```

### 问题 3：LLM API 调用失败

```bash
# 查看 Backend 日志
journalctl -u fota-backend -f

# 常见原因：
# - DEPLOYMENT_MODE 配置错误
# - LiteLLM Gateway 未启动（场景 A）
# - API Keys 无效或过期（场景 B）
# - 网络连接问题
```

### 问题 4：Nginx 502 Bad Gateway

```bash
# 检查 Backend 服务是否运行
sudo systemctl status fota-backend

# 检查端口监听
sudo netstat -tlnp | grep 8000

# 查看 Nginx 错误日志
sudo tail -f /var/log/nginx/fota-backend-error.log
```

---

## 🔗 相关文档

- [FOTA智能诊断平台_系统设计方案.md](../docs/FOTA智能诊断平台_系统设计方案.md) - 系统架构设计
- [FOTA智能诊断平台_可行性方案（修订版v6）.md](../docs/FOTA智能诊断平台_可行性方案（修订版v6）.md) - 可行性分析
- [FOTA_LLM_API中转方案.md](../docs/FOTA_LLM_API中转方案.md) - LLM API 中转架构
- [LLM_429限流防御方案.md](../docs/LLM_429限流防御方案.md) - 限流防御策略

---

## 📝 核心特性

- ✅ **多智能体协同**：Log Analytics + Jira + Doc Retrieval 三路证据融合
- ✅ **纯 Python async 编排**：高性能、易调试、完全可控
- ✅ **双供应商 Fallback**：Claude 主力 + OpenAI 备用
- ✅ **语义缓存**：预估 50~70% 缓存命中率，显著降低成本
- ✅ **时间窗口裁剪**：快速通道 2~5 分钟完成诊断（vs 30 分钟全量解析）
- ✅ **防幻觉护栏**：引用 ID 断言验证 + 置信度量化计算
- ✅ **可追溯证据链**：每条结论都能回溯到原始日志行号

---

## 🏗️ 架构说明

### 部署模式

Backend 支持两种部署模式（通过 `DEPLOYMENT_MODE` 环境变量配置）：

**场景 A（DEPLOYMENT_MODE=A）**：平台在国内
```
Backend (中国) → LiteLLM Gateway (美国) → Claude/OpenAI API
```

**场景 B（DEPLOYMENT_MODE=B）**：平台在海外
```
Backend (海外) → 直连 Claude/OpenAI API
```

### 技术栈

- **Web 框架**：FastAPI（原生 async/await）
- **LLM 集成**：统一抽象层（支持 Claude + OpenAI）
- **任务队列**：Arq（原生 async，与 FastAPI 无缝集成）
- **数据库**：PostgreSQL + pgvector
- **缓存**：Redis
- **对象存储**：MinIO / S3

---

## 📞 技术支持

如有问题，请查看：
1. 本 README 的故障排查章节
2. 项目 docs 目录下的详细设计文档
3. FastAPI 官方文档：https://fastapi.tiangolo.com/
