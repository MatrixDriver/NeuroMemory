"""Application configuration."""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    app_name: str = "NeuroMemory"
    debug: bool = False

    # Database
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://neuromemory:neuromemory@localhost:5432/neuromemory",
    )
    database_url_sync: str = os.getenv(
        "DATABASE_URL_SYNC",
        "postgresql://neuromemory:neuromemory@localhost:5432/neuromemory",
    )

    # Server
    host: str = "0.0.0.0"
    port: int = 8765

    # API Key
    api_key_prefix: str = "nm_"

    # Embedding (for pgvector)
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "siliconflow")
    embedding_dims: int = int(os.getenv("EMBEDDING_DIMS", "1024"))
    siliconflow_api_key: str = os.getenv("SILICONFLOW_API_KEY", "")
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_model: str = "BAAI/bge-m3"

    # LLM for classification (DeepSeek)
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
