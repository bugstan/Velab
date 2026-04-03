# PostgreSQL 安装与配置指南

## 📋 检查结果摘要

**检查时间**: 2026-04-03  
**操作系统**: Ubuntu 24.04.4 LTS (Noble Numbat)  
**PostgreSQL 状态**: ❌ **未安装**

---

## 🔍 当前状态

### 1. PostgreSQL 安装状态
- ✗ PostgreSQL 未安装
- ✗ `psql` 命令不可用
- ✗ 无 PostgreSQL 系统服务
- ✗ 无相关软件包

### 2. 项目数据库配置需求
根据 [`backend/.env`](../backend/.env:19) 配置文件，项目需要：
- **数据库名**: `fota_db`
- **用户名**: `postgres`
- **密码**: `fota_password`
- **主机**: `localhost`
- **端口**: `5432`
- **用途**: 存储案件元数据、标准事件表、向量索引

### 3. 扩展需求
- **pgvector**: 用于向量相似度搜索（语义缓存、知识检索）

---

## 🚀 完整安装指南

### 步骤 1: 安装 PostgreSQL 16

```bash
# 更新软件包列表
sudo apt update

# 安装 PostgreSQL 16 和相关工具
sudo apt install -y postgresql-16 postgresql-contrib-16 postgresql-client-16

# 验证安装
psql --version
```

**预期输出**: `psql (PostgreSQL) 16.x`

---

### 步骤 2: 启动并启用 PostgreSQL 服务

```bash
# 启动 PostgreSQL 服务
sudo systemctl start postgresql

# 设置开机自启
sudo systemctl enable postgresql

# 检查服务状态
sudo systemctl status postgresql
```

**预期输出**: `Active: active (running)`

---

### 步骤 3: 配置数据库用户和密码

```bash
# 切换到 postgres 用户
sudo -u postgres psql

# 在 psql 提示符下执行以下 SQL 命令：
```

```sql
-- 设置 postgres 用户密码
ALTER USER postgres WITH PASSWORD 'fota_password';

-- 退出 psql
\q
```

---

### 步骤 4: 创建 fota_db 数据库

```bash
# 创建数据库
sudo -u postgres createdb fota_db

# 或者在 psql 中执行：
sudo -u postgres psql -c "CREATE DATABASE fota_db OWNER postgres;"
```

---

### 步骤 5: 安装 pgvector 扩展

```bash
# 安装编译工具和依赖
sudo apt install -y build-essential postgresql-server-dev-16 git

# 克隆 pgvector 仓库
cd /tmp
git clone --branch v0.7.0 https://github.com/pgvector/pgvector.git
cd pgvector

# 编译并安装
make
sudo make install

# 在数据库中启用扩展
sudo -u postgres psql -d fota_db -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

**验证 pgvector 安装**:
```bash
sudo -u postgres psql -d fota_db -c "SELECT * FROM pg_extension WHERE extname = 'vector';"
```

---

### 步骤 6: 配置 PostgreSQL 允许本地连接

编辑 PostgreSQL 配置文件以允许密码认证：

```bash
# 编辑 pg_hba.conf
sudo nano /etc/postgresql/16/main/pg_hba.conf
```

确保以下行存在（通常在文件末尾）：
```
# TYPE  DATABASE        USER            ADDRESS                 METHOD
local   all             postgres                                md5
host    all             all             127.0.0.1/32            md5
host    all             all             ::1/128                 md5
```

**重启 PostgreSQL 使配置生效**:
```bash
sudo systemctl restart postgresql
```

---

### 步骤 7: 测试数据库连接

```bash
# 使用密码连接测试
PGPASSWORD=fota_password psql -h localhost -U postgres -d fota_db -c "SELECT version();"

# 测试 pgvector 扩展
PGPASSWORD=fota_password psql -h localhost -U postgres -d fota_db -c "SELECT vector_dims('[1,2,3]'::vector);"
```

**预期输出**:
- 第一条命令应显示 PostgreSQL 版本信息
- 第二条命令应返回 `3`（向量维度）

---

## 📝 数据库初始化脚本

创建项目所需的基础表结构：

```sql
-- 连接到 fota_db
\c fota_db

-- 创建案件元数据表
CREATE TABLE IF NOT EXISTS cases (
    id SERIAL PRIMARY KEY,
    case_id VARCHAR(100) UNIQUE NOT NULL,
    vin VARCHAR(17),
    vehicle_model VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50),
    metadata JSONB
);

-- 创建标准事件表
CREATE TABLE IF NOT EXISTS standard_events (
    id SERIAL PRIMARY KEY,
    event_code VARCHAR(50) UNIQUE NOT NULL,
    event_name VARCHAR(200),
    description TEXT,
    category VARCHAR(100),
    severity VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建向量索引表（用于语义缓存）
CREATE TABLE IF NOT EXISTS semantic_cache (
    id SERIAL PRIMARY KEY,
    query_hash VARCHAR(64) UNIQUE NOT NULL,
    query_text TEXT NOT NULL,
    query_embedding vector(1536),  -- OpenAI embedding 维度
    response_text TEXT,
    cache_type VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    hit_count INTEGER DEFAULT 0
);

-- 创建向量相似度搜索索引
CREATE INDEX IF NOT EXISTS semantic_cache_embedding_idx 
ON semantic_cache USING ivfflat (query_embedding vector_cosine_ops)
WITH (lists = 100);

-- 创建知识库向量表
CREATE TABLE IF NOT EXISTS knowledge_vectors (
    id SERIAL PRIMARY KEY,
    source_type VARCHAR(50),  -- 'jira', 'document', 'log'
    source_id VARCHAR(200),
    content TEXT,
    embedding vector(1536),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建知识库向量索引
CREATE INDEX IF NOT EXISTS knowledge_vectors_embedding_idx 
ON knowledge_vectors USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- 创建索引以提升查询性能
CREATE INDEX IF NOT EXISTS cases_case_id_idx ON cases(case_id);
CREATE INDEX IF NOT EXISTS cases_vin_idx ON cases(vin);
CREATE INDEX IF NOT EXISTS cases_created_at_idx ON cases(created_at);
CREATE INDEX IF NOT EXISTS semantic_cache_expires_at_idx ON semantic_cache(expires_at);
CREATE INDEX IF NOT EXISTS knowledge_vectors_source_idx ON knowledge_vectors(source_type, source_id);
```

**保存为脚本并执行**:
```bash
# 保存上述 SQL 到文件
sudo nano /tmp/init_fota_db.sql

# 执行初始化脚本
PGPASSWORD=fota_password psql -h localhost -U postgres -d fota_db -f /tmp/init_fota_db.sql
```

---

## ✅ 验证清单

完成安装后，请逐项验证：

- [ ] PostgreSQL 16 已安装并运行
- [ ] `psql --version` 显示版本号
- [ ] `sudo systemctl status postgresql` 显示 active (running)
- [ ] postgres 用户密码已设置为 `fota_password`
- [ ] fota_db 数据库已创建
- [ ] pgvector 扩展已安装并启用
- [ ] 可以使用密码从 localhost 连接数据库
- [ ] 基础表结构已创建
- [ ] 向量索引已创建

---

## 🔧 常见问题排查

### 问题 1: 无法连接数据库
```bash
# 检查 PostgreSQL 是否运行
sudo systemctl status postgresql

# 检查端口是否监听
sudo netstat -tlnp | grep 5432

# 查看 PostgreSQL 日志
sudo tail -f /var/log/postgresql/postgresql-16-main.log
```

### 问题 2: 密码认证失败
```bash
# 确认 pg_hba.conf 配置正确
sudo cat /etc/postgresql/16/main/pg_hba.conf | grep -v "^#" | grep -v "^$"

# 重启服务
sudo systemctl restart postgresql
```

### 问题 3: pgvector 扩展安装失败
```bash
# 确认 postgresql-server-dev 已安装
dpkg -l | grep postgresql-server-dev

# 检查编译错误日志
cd /tmp/pgvector
make clean
make 2>&1 | tee build.log
```

### 问题 4: 向量索引创建失败
```sql
-- 检查 pgvector 扩展是否启用
SELECT * FROM pg_extension WHERE extname = 'vector';

-- 如果未启用，手动创建
CREATE EXTENSION IF NOT EXISTS vector;

-- 重新创建索引
DROP INDEX IF EXISTS semantic_cache_embedding_idx;
CREATE INDEX semantic_cache_embedding_idx 
ON semantic_cache USING ivfflat (query_embedding vector_cosine_ops)
WITH (lists = 100);
```

---

## 📚 相关文档

- [PostgreSQL 官方文档](https://www.postgresql.org/docs/16/)
- [pgvector GitHub](https://github.com/pgvector/pgvector)
- [Ubuntu PostgreSQL 安装指南](https://www.postgresql.org/download/linux/ubuntu/)
- 项目配置文件: [`backend/.env`](../backend/.env)

---

## 🎯 下一步操作

1. **立即执行**: 按照上述步骤安装 PostgreSQL 和 pgvector
2. **验证连接**: 使用测试命令确认数据库可正常访问
3. **初始化数据**: 运行初始化脚本创建表结构
4. **更新配置**: 确认 [`backend/.env`](../backend/.env) 中的数据库配置正确
5. **启动后端**: 运行 `cd backend && python main.py` 测试后端服务

---

**生成时间**: 2026-04-03  
**文档版本**: 1.0
