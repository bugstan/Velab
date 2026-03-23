import os
from dotenv import load_dotenv

load_dotenv()

MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.io/v1")
MINIMAX_MODEL = os.getenv("MINIMAX_MODEL", "MiniMax-M2.5")

# 编排 / 流式是否使用 *-highspeed 变体（与 MiniMax 文档一致，通常延迟更低）
MINIMAX_USE_HIGHSPEED = os.getenv("MINIMAX_USE_HIGHSPEED", "true").lower() in ("1", "true", "yes")

# 编排器是否走流式 API（首包/TTFB 更早出现；tool_calls 在流结束后聚合，总耗时常与阻塞式接近）
MINIMAX_ORCHESTRATOR_STREAM = os.getenv("MINIMAX_ORCHESTRATOR_STREAM", "false").lower() in (
    "1",
    "true",
    "yes",
)

SCENARIO_AGENT_MAP: dict[str, list[str]] = {
    "fota-diagnostic": ["log_analytics"],
    "fota-jira": ["log_analytics", "jira_knowledge"],
    "fleet-analytics": ["log_analytics"],
    "ces-demo": ["log_analytics", "jira_knowledge"],
    "data-acquisitions": ["log_analytics"],
}
