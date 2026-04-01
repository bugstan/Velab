# Velab LLM Gateway (LiteLLM Proxy)

该目录提供了 Velab 项目专用的 API 中转层配置，用于解决跨境网络访问、模型 Fallback 以及多供应商统一接口问题。

## 快速启动 (无 Docker)

1.  **安装 LiteLLM**:
    ```bash
    pip install 'litellm[proxy]'
    ```

2.  **配置环境**:
    复制 `.env.example` 为 `.env` 并填写相关 API Key。

3.  **运行中转服务器**:
    ```bash
    litellm --config config.yaml --port 4000
    ```

4.  **在 Velab 后端中使用**:
    修改 `Velab/backend/.env`:
    ```env
    # 使用中转后的 OpenAI 兼容接口
    MINIMAX_BASE_URL=http://localhost:4000
    MINIMAX_API_KEY=sk-velab-gateway-123456
    ```

## 核心特性
- **统一协议**: 将 Claude、MiniMax 全部统一为 OpenAI 格式接口。
- **自动 Fallback**: 当 Claude 触发 429 或 500 时，自动切换至 GPT-4o 或 MiniMax。
- **重试机制**: 自带请求重试与超时保护。