# Velab LLM Gateway (LiteLLM Proxy)

该目录提供了 Velab 项目专用的 LLM API 中转层配置，用于解决跨境网络访问、模型 Fallback 以及多供应商统一接口问题。

---

## 📋 目录结构

```
gateway/
├── config.yaml              # LiteLLM 模型路由配置
├── .env.example             # 环境变量配置示例
├── README.md                # 本文档
├── gateway功能检查报告.md    # 功能完成度报告
├── systemd/
│   └── litellm.service      # systemd 服务配置
├── nginx/
│   └── litellm.conf         # Nginx 反向代理配置
└── scripts/
    ├── start.sh             # 开发环境启动脚本
    ├── deploy.sh            # 生产环境自动部署脚本
    └── validate_config.sh   # 配置验证脚本
```

---

## 🚀 快速启动（开发环境）

### 1. 安装 LiteLLM

```bash
pip install 'litellm[proxy]'
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入真实的 API Keys
```

### 3. 验证配置（可选但推荐）

```bash
# 运行配置验证脚本
chmod +x scripts/validate_config.sh
./scripts/validate_config.sh

# 验证通过后会显示：
# ✓ 配置验证通过，可以启动服务
```

### 4. 启动服务

**方式 A：使用启动脚本（推荐）**
```bash
chmod +x scripts/start.sh
./scripts/start.sh
```

**方式 B：直接运行**
```bash
litellm --config config.yaml --port 4000
```

### 5. 验证服务

```bash
# 健康检查
curl http://localhost:4000/health

# 测试 LLM 调用
curl http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-litellm-master-xxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "router-model",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

---

## 🏭 生产环境部署

### 方式 A：自动部署（推荐）

使用 [`deploy.sh`](scripts/deploy.sh) 脚本一键部署：

```bash
# 1. 进入 gateway 目录
cd gateway

# 2. 运行部署脚本
sudo ./scripts/deploy.sh

# 3. 编辑配置文件，填入真实 API Keys
sudo nano /opt/litellm-proxy/.env

# 4. 启动服务
sudo systemctl start litellm

# 5. 查看状态
sudo systemctl status litellm
```

**deploy.sh 自动完成的操作**：
- ✅ 检查系统依赖（Python3）
- ✅ 创建专用用户 `litellm`
- ✅ 创建部署目录 `/opt/litellm-proxy`
- ✅ 配置 Python 虚拟环境
- ✅ 安装 LiteLLM
- ✅ 复制配置文件
- ✅ 安装 systemd 服务

---

### 方式 B：手动部署

#### 前置准备

1. **服务器要求**
   - 操作系统：Linux（推荐 Ubuntu 22.04 / Debian 12）
   - 位置：美国 CN2 GIA 服务器（或其他海外服务器）
   - 内存：≥ 2GB
   - 磁盘：≥ 10GB

2. **域名与 DNS**
   - 准备一个域名（如 `llm-proxy.example.com`）
   - DNS 托管在 Cloudflare（启用代理模式，橙色云朵）

#### 步骤 1：创建专用用户

```bash
sudo useradd -r -s /sbin/nologin litellm
sudo mkdir -p /opt/litellm-proxy/{logs,systemd,nginx,scripts}
sudo chown -R litellm:litellm /opt/litellm-proxy
```

### 步骤 2：安装 LiteLLM

```bash
# 创建 Python 虚拟环境
sudo -u litellm python3 -m venv /opt/litellm-proxy/venv

# 安装 LiteLLM
sudo -u litellm /opt/litellm-proxy/venv/bin/pip install 'litellm[proxy]'

# 验证安装
sudo -u litellm /opt/litellm-proxy/venv/bin/litellm --version
```

### 步骤 3：部署配置文件

```bash
# 复制配置文件到生产目录
sudo cp config.yaml /opt/litellm-proxy/
sudo cp .env /opt/litellm-proxy/
sudo chmod 600 /opt/litellm-proxy/.env
sudo chown litellm:litellm /opt/litellm-proxy/{config.yaml,.env}
```

#### 步骤 4：配置 systemd 服务

```bash
# 复制 systemd 服务文件
sudo cp systemd/litellm.service /etc/systemd/system/

# 重载 systemd
sudo systemctl daemon-reload

# 启用并启动服务
sudo systemctl enable litellm
sudo systemctl start litellm

# 查看状态
sudo systemctl status litellm

# 查看日志
journalctl -u litellm -f
```

#### 步骤 5：配置 Nginx + Cloudflare SSL

**5.1 生成 Cloudflare Origin Certificate**

1. 登录 Cloudflare Dashboard
2. 选择域名 → SSL/TLS → Origin Server
3. 点击 "Create Certificate"
4. 保存证书和私钥：

```bash
sudo mkdir -p /etc/nginx/ssl
sudo nano /etc/nginx/ssl/origin-cert.pem     # 粘贴 Origin Certificate
sudo nano /etc/nginx/ssl/origin-key.pem      # 粘贴 Private Key
sudo chmod 600 /etc/nginx/ssl/origin-key.pem
```

**5.2 配置 Nginx**

```bash
# 安装 Nginx
sudo apt install nginx

# 复制配置文件
sudo cp nginx/litellm.conf /etc/nginx/sites-available/

# 修改域名（替换 llm-proxy.example.com 为你的域名）
sudo nano /etc/nginx/sites-available/litellm.conf

# 启用站点
sudo ln -s /etc/nginx/sites-available/litellm.conf /etc/nginx/sites-enabled/

# 测试配置
sudo nginx -t

# 重载 Nginx
sudo systemctl reload nginx
```

**5.3 配置 Cloudflare SSL 模式**

在 Cloudflare Dashboard 中：
- SSL/TLS → Overview → 选择 **Full (Strict)** 模式

#### 步骤 6：验证部署

```bash
# 从国内测试（通过 Cloudflare CDN）
curl https://llm-proxy.example.com/health

# 测试 LLM 调用
curl https://llm-proxy.example.com/v1/chat/completions \
  -H "Authorization: Bearer sk-litellm-master-xxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "router-model",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

---

## 🔧 运维命令速查

### systemd 服务管理

```bash
# 启动 / 停止 / 重启
sudo systemctl start litellm
sudo systemctl stop litellm
sudo systemctl restart litellm

# 查看运行状态
sudo systemctl status litellm

# 实时日志（调试利器）
journalctl -u litellm -f

# 查看最近 100 行日志
journalctl -u litellm -n 100

# 修改配置后重启
sudo systemctl restart litellm
```

### Nginx 管理

```bash
# 测试配置
sudo nginx -t

# 重载配置（不中断服务）
sudo systemctl reload nginx

# 重启 Nginx
sudo systemctl restart nginx

# 查看日志
sudo tail -f /var/log/nginx/litellm-access.log
sudo tail -f /var/log/nginx/litellm-error.log
```

### 升级 LiteLLM

```bash
sudo -u litellm /opt/litellm-proxy/venv/bin/pip install --upgrade 'litellm[proxy]'
sudo systemctl restart litellm
```

### 配置验证

```bash
# 验证配置文件语法和环境变量
cd gateway
./scripts/validate_config.sh

# 详细输出模式
./scripts/validate_config.sh --verbose

# 验证指定配置文件
./scripts/validate_config.sh --config /path/to/config.yaml
```

**验证内容**：
- ✅ YAML 语法检查
- ✅ 配置结构验证（必需字段）
- ✅ 环境变量检查
- ✅ API Keys 格式验证

---

## 📊 监控与日志

### 查看 LiteLLM 日志

```bash
# 实时日志
journalctl -u litellm -f

# 按时间范围查询
journalctl -u litellm --since "2026-04-02 10:00:00" --until "2026-04-02 11:00:00"

# 只看错误日志
journalctl -u litellm -p err
```

### Prometheus 指标（可选）

LiteLLM 内置 Prometheus 指标导出，访问：
```
http://localhost:4000/metrics
```

关键指标：
- `litellm_requests_total` - 总请求数
- `litellm_spend_total` - 总花费
- `litellm_deployment_failure_total` - 失败次数

---

## 🔐 安全最佳实践

1. **API Keys 保护**
   - `.env` 文件权限设置为 `600`
   - 不要提交 `.env` 到版本库
   - 定期轮换 API Keys

2. **网络安全**
   - Nginx 配置中已限制仅允许 Cloudflare IP 访问
   - 定期更新 Cloudflare IP 白名单

3. **服务隔离**
   - LiteLLM 运行在专用用户 `litellm` 下
   - systemd 配置了安全加固选项

4. **日志审计**
   - 所有请求都记录在 Nginx access log
   - journald 保留 systemd 服务日志

---

## 🚨 故障排查

### 问题 1：服务无法启动

```bash
# 查看详细错误
journalctl -u litellm -n 50

# 常见原因：
# - .env 文件缺失或格式错误
# - API Keys 未配置
# - 端口 4000 被占用
```

### 问题 2：Nginx 502 Bad Gateway

```bash
# 检查 LiteLLM 服务是否运行
sudo systemctl status litellm

# 检查端口监听
sudo netstat -tlnp | grep 4000

# 查看 Nginx 错误日志
sudo tail -f /var/log/nginx/litellm-error.log
```

### 问题 3：LLM API 调用失败

```bash
# 查看 LiteLLM 日志
journalctl -u litellm -f

# 常见原因：
# - API Keys 无效或过期
# - 网络连接问题（检查服务器到 api.anthropic.com / api.openai.com 的连通性）
# - 速率限制（429 错误）
```

---

## 🔗 相关文档

- [LiteLLM 官方文档](https://docs.litellm.ai/)
- [FOTA_LLM_API中转方案.md](../docs/FOTA_LLM_API中转方案.md) - 完整架构设计
- [LLM_429限流防御方案.md](../docs/LLM_429限流防御方案.md) - 限流防御策略

---

## 📝 核心特性

- ✅ **统一协议**：将 Claude / OpenAI 等模型统一为 OpenAI 格式接口
- ✅ **自动 Fallback**：Claude 触发 429 时自动切换到 OpenAI
- ✅ **Key Pool 轮转**：多个 API Key 负载均衡，提升并发能力
- ✅ **重试机制**：自带请求重试与超时保护
- ✅ **跨境优化**：部署在海外服务器，减少跨境请求次数
- ✅ **安全加固**：Cloudflare SSL + IP 白名单 + systemd 安全选项

---

## 📞 技术支持

如有问题，请查看：
1. 本 README 的故障排查章节
2. LiteLLM 官方文档
3. 项目 docs 目录下的详细设计文档
