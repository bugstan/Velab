---
name: velab-devops-operator
description: 平台基础设施和运维部署专家。负责管理 systemd 服务控制、Nginx 反向代理、LiteLLM Gateway 和系统级环境变量调试。
---

# Velab DevOps 运维操作指南

针对生产服务器 (`deploy` 侧)、网关或系统级服务的部署与调试辅助。

## 1. Systemd 核心守护进程管理
Velab 的核心进程受控于系统服务（位于 `/etc/systemd/system/`）：
- **后端服务**：`fota-backend.service` 
- **网关服务**：`litellm.service` 

### 常用管理指引：
- 服务状态诊断：`sudo systemctl status <service-name>`
- 实时日志查看 (排障必备)：`journalctl -u <service-name> -f -n 100`

若更新了配置文件或应用核心依赖，务必执行重启：
`sudo systemctl restart fota-backend` 

## 2. Nginx 反向代理与 SSL
Nginx 承担所有对外露出的 HTTP/HTTPS 流量管理（配置位于 `gateway/nginx/` 和 `backend/nginx/`）。
- **常规路径**：
  - 后端接口通过 `/api` 或特定 proxy 映射转发至内部 `127.0.0.1:8000`。
  - 网关转发至内部 `4000` 端口。
- **排障技巧**：如果 Web 遇到 `502 Bad Gateway`，第一步确认对应服务进程是否存在，第二步排查 `/var/log/nginx/` 错误日志，定位是否是被 Let's Encrypt / Cloudflare SSL 终结时发生的代理头畸变。

## 3. LiteLLM Gateway 管理机制
Gateway 负责模型统一路由和并发控制，是极关键的一环：
- **核心文件**：`gateway/config.yaml` 统领全套模型 fallback 与 API Key 轮询机制。
- **安全性管控**：当引入新的 LLM API Keys（如 `ANTHROPIC_API_KEY_1`），必须配置于 `.env` 且确保属主权限为 `600`。绝不能明文留存在代码仓库内。
- **429 防御**：参考 `LLM_429限流防御方案.md`，若日志侦测到频发超时限流，需动态调度轮询策略。

## 4. 自动化部署脚本与网络架构
- `scripts/deploy-all.sh` 等脚本管理着全流水线。在执行自动化脚本修改时，务必兼容 Ubuntu 22.04 / Debian 12 核心的 APT 生态环境结构。
- 保证应用对外的仅在 Nginx 层处理公网流量，底层 PostgreSQL/Redis/FastAPI 只绑定 `127.0.0.1`，确保最高等级的默认安全。
