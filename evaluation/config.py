"""Evaluation configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class EvalConfig:
    """All evaluation settings, populated from env vars with sensible defaults."""

    # Database
    database_url: str = field(
        default_factory=lambda: os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://neuromemory:neuromemory@localhost:5432/neuromemory_eval",
        )
    )

    # Embedding provider
    embedding_provider: str = field(
        default_factory=lambda: os.environ.get("EMBEDDING_PROVIDER", "siliconflow")
    )
    embedding_api_key: str = field(
        default_factory=lambda: os.environ.get("EMBEDDING_API_KEY", "")
    )
    embedding_model: str = field(
        default_factory=lambda: os.environ.get("EMBEDDING_MODEL", "")
    )

    # LLM for memory extraction + answer generation
    llm_api_key: str = field(
        default_factory=lambda: os.environ.get("LLM_API_KEY", "")
    )
    llm_model: str = field(
        default_factory=lambda: os.environ.get("LLM_MODEL", "deepseek-chat")
    )
    llm_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "LLM_BASE_URL", "https://api.deepseek.com/v1"
        )
    )

    # LLM Judge (GPT-4o-mini by default)
    judge_api_key: str = field(
        default_factory=lambda: os.environ.get("JUDGE_API_KEY", "")
    )
    judge_model: str = field(
        default_factory=lambda: os.environ.get("JUDGE_MODEL", "gpt-4o-mini")
    )
    judge_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "JUDGE_BASE_URL", "https://api.openai.com/v1"
        )
    )

    # Data paths
    locomo_data_path: str = field(
        default_factory=lambda: os.environ.get(
            "LOCOMO_DATA_PATH", "evaluation/data/locomo10.json"
        )
    )
    longmemeval_data_path: str = field(
        default_factory=lambda: os.environ.get(
            "LONGMEMEVAL_DATA_PATH", "evaluation/data/longmemeval_s_cleaned.json"
        )
    )

    # Output
    results_dir: str = field(
        default_factory=lambda: os.environ.get("RESULTS_DIR", "evaluation/results")
    )

    # Pipeline settings
    extraction_batch_size: int = 50
    recall_limit: int = 20
    graph_enabled: bool = field(
        default_factory=lambda: os.environ.get("GRAPH_ENABLED", "0") == "1"
    )
    # Recency decay rate in days (default 365 for benchmarks; production default is 30)
    decay_rate_days: int = field(
        default_factory=lambda: int(os.environ.get("DECAY_RATE_DAYS", "365"))
    )

    # Optional separate LLM for answer generation (e.g. deepseek-reasoner)
    answer_llm_model: str = field(
        default_factory=lambda: os.environ.get("ANSWER_LLM_MODEL", "")
    )
    answer_llm_api_key: str = field(
        default_factory=lambda: os.environ.get("ANSWER_LLM_API_KEY", "")
    )
    answer_llm_base_url: str = field(
        default_factory=lambda: os.environ.get("ANSWER_LLM_BASE_URL", "")
    )
