"""
FOTA 智能诊断平台 — 统一配置模块

本模块使用 pydantic-settings 管理应用配置，支持从 .env 文件和环境变量读取配置项。
提供两种部署模式的自动切换：
- 场景 A：国内部署，通过 LiteLLM 网关中转访问 LLM 服务
- 场景 B：海外部署，直连 LLM 供应商 API

主要功能：
1. 数据库连接配置（PostgreSQL、Redis）
2. LLM 服务配置（支持多供应商）
3. 场景化 Agent 映射配置
4. 根据部署模式自动选择 API 端点和密钥

作者：FOTA 诊断平台团队
创建时间：2025
最后更新：2025
"""

from enum import Enum
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class DeploymentMode(str, Enum):
    """
    部署模式枚举
    
    定义系统的两种部署场景，影响 LLM 服务的访问方式：
    - SCENARIO_A: 国内部署模式，通过 LiteLLM 网关中转
    - SCENARIO_B: 海外部署模式，直连供应商 API
    """
    SCENARIO_A = "A"  # 平台在国内，走 LiteLLM 中转
    SCENARIO_B = "B"  # 平台在海外，直连供应商


class Settings(BaseSettings):
    """
    应用配置类
    
    使用 pydantic-settings 自动从 .env 文件和环境变量加载配置。
    所有配置项都有合理的默认值，可通过环境变量覆盖。
    
    配置分类：
    1. 基础配置：项目名称、部署模式
    2. 数据库配置：PostgreSQL、Redis 连接参数
    3. LLM 配置：多供应商 API 密钥和端点
    4. 编排器配置：流式输出等行为控制
    
    派生属性：
    - DATABASE_URL: 自动生成的数据库连接字符串
    - LLM_BASE_URL: 根据部署模式自动选择的 LLM 端点
    - LLM_API_KEY: 根据部署模式自动选择的 API 密钥
    """
    # ── 基础配置 ──
    PROJECT_NAME: str = "FOTA 智能诊断平台"
    DEPLOYMENT_MODE: DeploymentMode = DeploymentMode.SCENARIO_A

    # ── 数据库配置（待接入） ──
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "fota_password"
    POSTGRES_DB: str = "fota_db"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    # ── Redis 配置（待接入） ──
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # ── LLM 配置 ──
    LITELLM_BASE_URL: Optional[str] = "https://gateway.fota.com/v1"
    LITELLM_API_KEY: Optional[str] = "sk-fota-master-key"

    ANTHROPIC_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    # ── 编排器 ──
    ORCHESTRATOR_STREAM: bool = False

    # ── 派生属性 ──

    @property
    def DATABASE_URL(self) -> str:
        """
        生成 PostgreSQL 异步连接字符串
        
        使用 asyncpg 驱动，供后续 RAG 检索和数据持久化功能使用。
        
        Returns:
            str: 格式为 postgresql+asyncpg://user:password@host:port/database 的连接串
        """
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def LLM_BASE_URL(self) -> Optional[str]:
        """
        根据部署模式自动选择 LLM 服务的 Base URL
        
        - 场景 A（国内）：返回 LiteLLM 网关地址
        - 场景 B（海外）：返回 None，使用 OpenAI SDK 默认端点
        
        Returns:
            Optional[str]: LLM API 的基础 URL，场景 B 返回 None
        """
        if self.DEPLOYMENT_MODE == DeploymentMode.SCENARIO_A:
            return self.LITELLM_BASE_URL
        # 场景 B 直连模式下，OpenAI SDK 默认指向 api.openai.com
        return None

    @property
    def LLM_API_KEY(self) -> Optional[str]:
        """
        根据部署模式自动选择 LLM 服务的 API Key
        
        - 场景 A（国内）：返回 LiteLLM 网关的统一密钥
        - 场景 B（海外）：返回第一个可用的供应商密钥（优先 Anthropic）
        
        Returns:
            Optional[str]: LLM API 密钥
        """
        if self.DEPLOYMENT_MODE == DeploymentMode.SCENARIO_A:
            return self.LITELLM_API_KEY
        # 场景 B 需区分供应商，此处取第一个可用 Key
        return self.ANTHROPIC_API_KEY or self.OPENAI_API_KEY

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()


# ── 场景化 Agent 映射（Velab 编排层使用）──
SCENARIO_AGENT_MAP: dict[str, list[str]] = {
    "fota-diagnostic": ["log_analytics"],
    "fota-jira": ["log_analytics", "jira_knowledge"],
    "fleet-analytics": ["log_analytics"],
    "ces-demo": ["log_analytics", "jira_knowledge"],
    "data-acquisitions": ["log_analytics"],
}
