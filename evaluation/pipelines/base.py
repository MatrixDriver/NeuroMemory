"""Base pipeline utilities: cleanup, timestamps, checkpoint, NM factory."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from sqlalchemy import text

from neuromemory import NeuroMemory, OpenAILLM
from neuromemory.providers.embedding import EmbeddingProvider

from evaluation.config import EvalConfig

logger = logging.getLogger(__name__)


def create_embedding_provider(cfg: EvalConfig) -> EmbeddingProvider:
    """Create embedding provider from config."""
    if cfg.embedding_provider == "sentence_transformer":
        from neuromemory.providers.sentence_transformer import SentenceTransformerEmbedding
        model = cfg.embedding_model or "all-MiniLM-L6-v2"
        return SentenceTransformerEmbedding(model=model)
    elif cfg.embedding_provider == "openai":
        from neuromemory import OpenAIEmbedding
        kwargs = {"api_key": cfg.embedding_api_key}
        if cfg.embedding_model:
            kwargs["model"] = cfg.embedding_model
        if cfg.embedding_base_url:
            kwargs["base_url"] = cfg.embedding_base_url
        return OpenAIEmbedding(**kwargs)
    else:
        from neuromemory import SiliconFlowEmbedding
        kwargs = {"api_key": cfg.embedding_api_key}
        if cfg.embedding_model:
            kwargs["model"] = cfg.embedding_model
        return SiliconFlowEmbedding(**kwargs)


def create_nm(cfg: EvalConfig) -> NeuroMemory:
    """Create a NeuroMemory instance from config (no auto-extraction)."""
    embedding = create_embedding_provider(cfg)
    llm = OpenAILLM(
        api_key=cfg.llm_api_key,
        model=cfg.llm_model,
        base_url=cfg.llm_base_url,
    )
    return NeuroMemory(
        database_url=cfg.database_url,
        embedding=embedding,
        llm=llm,
        graph_enabled=cfg.graph_enabled,
    )


def create_judge_llm(cfg: EvalConfig) -> OpenAILLM:
    """Create LLM instance for judge evaluation."""
    return OpenAILLM(
        api_key=cfg.judge_api_key,
        model=cfg.judge_model,
        base_url=cfg.judge_base_url,
    )


async def cleanup_user(nm: NeuroMemory, user_id: str) -> None:
    """Delete all data for a user to ensure clean evaluation."""
    async with nm._db.session() as session:
        for table in [
            "conversations",
            "conversation_sessions",
            "embeddings",
            "graph_nodes",
            "graph_edges",
        ]:
            await session.execute(
                text(f"DELETE FROM {table} WHERE user_id = :uid"),
                {"uid": user_id},
            )
        # key_values uses scope_id instead of user_id
        await session.execute(
            text("DELETE FROM key_values WHERE scope_id = :uid"),
            {"uid": user_id},
        )
    logger.info("Cleaned up user: %s", user_id)


async def set_timestamps(
    nm: NeuroMemory,
    user_id: str,
    session_id: str,
    timestamp: datetime,
) -> None:
    """Backfill created_at for conversations and embeddings to match dataset time."""
    async with nm._db.session() as session:
        await session.execute(
            text(
                "UPDATE conversations SET created_at = :ts "
                "WHERE user_id = :uid AND session_id = :sid"
            ),
            {"ts": timestamp, "uid": user_id, "sid": session_id},
        )
        await session.execute(
            text(
                "UPDATE conversation_sessions SET created_at = :ts "
                "WHERE user_id = :uid AND session_id = :sid"
            ),
            {"ts": timestamp, "uid": user_id, "sid": session_id},
        )


async def set_embedding_timestamps(
    nm: NeuroMemory,
    user_id: str,
    timestamp: datetime,
    embedding_ids: list[str] | None = None,
) -> None:
    """Backfill created_at on embedding records."""
    async with nm._db.session() as session:
        if embedding_ids:
            await session.execute(
                text(
                    "UPDATE embeddings SET created_at = :ts "
                    "WHERE user_id = :uid AND id = ANY(:ids)"
                ),
                {"ts": timestamp, "uid": user_id, "ids": embedding_ids},
            )
        else:
            await session.execute(
                text(
                    "UPDATE embeddings SET created_at = :ts "
                    "WHERE user_id = :uid"
                ),
                {"ts": timestamp, "uid": user_id},
            )


def load_checkpoint(path: str) -> dict:
    """Load checkpoint from JSON file, or return empty state."""
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"completed": [], "results": []}


def save_checkpoint(path: str, checkpoint: dict) -> None:
    """Save checkpoint atomically."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(checkpoint, f, indent=2, default=str)
    os.replace(tmp, path)
