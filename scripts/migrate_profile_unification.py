"""数据迁移脚本：Profile 统一架构

将 KV Profile 和 Emotion Profile 数据迁移到 fact + trait 统一存储。

用法:
    uv run python scripts/migrate_profile_unification.py --database-url "postgresql+asyncpg://..." --dry-run
    uv run python scripts/migrate_profile_unification.py --database-url "postgresql+asyncpg://..."
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)


async def migrate(database_url: str, dry_run: bool = False, embedding_provider=None):
    """执行迁移。"""
    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    stats = {
        "facts_created": 0,
        "traits_created": 0,
        "watermarks_migrated": 0,
        "users_processed": 0,
        "errors": [],
    }

    async with async_session() as session:
        async with session.begin():
            # 1. 获取所有有 profile 数据的用户
            kv_users = await session.execute(
                sql_text("SELECT DISTINCT scope_id FROM key_values WHERE namespace = 'profile'")
            )
            ep_users = await session.execute(
                sql_text("SELECT DISTINCT user_id FROM emotion_profiles")
            )
            all_users = set(r.scope_id for r in kv_users.fetchall()) | set(r.user_id for r in ep_users.fetchall())

            logger.info("找到 %d 个需要迁移的用户", len(all_users))

            for user_id in all_users:
                try:
                    user_stats = await _migrate_user(session, user_id, embedding_provider)
                    stats["facts_created"] += user_stats["facts"]
                    stats["traits_created"] += user_stats["traits"]
                    stats["watermarks_migrated"] += user_stats["watermarks"]
                    stats["users_processed"] += 1
                except Exception as e:
                    logger.error("迁移用户 %s 失败: %s", user_id, e, exc_info=True)
                    stats["errors"].append({"user_id": user_id, "error": str(e)})

            if dry_run:
                logger.info("Dry-run 模式，回滚所有变更")
                await session.rollback()
            # else: session.begin() context manager 自动 commit

    await engine.dispose()

    logger.info("迁移完成: %s", stats)
    return stats


async def _migrate_user(session: AsyncSession, user_id: str, embedding_provider=None) -> dict:
    """迁移单个用户的数据。"""
    stats = {"facts": 0, "traits": 0, "watermarks": 0}
    now = datetime.now(timezone.utc)

    # --- KV Profile -> fact/trait ---
    kv_result = await session.execute(
        sql_text("SELECT key, value FROM key_values WHERE namespace = 'profile' AND scope_id = :uid"),
        {"uid": user_id},
    )
    kv_items = {r.key: r.value for r in kv_result.fetchall()}

    # identity, occupation -> fact
    for key, category in [("identity", "identity"), ("occupation", "work")]:
        value = kv_items.get(key)
        if value and isinstance(value, str) and value.strip():
            content = f"用户{key}: {value}" if key == "identity" else value
            await _create_memory(session, user_id, content, "fact", {"category": category, "source": "migration"}, now, embedding_provider)
            stats["facts"] += 1

    # relationships -> fact
    relationships = kv_items.get("relationships")
    if relationships and isinstance(relationships, list):
        for rel in relationships:
            if rel and isinstance(rel, str) and rel.strip():
                await _create_memory(session, user_id, rel, "fact", {"category": "relationship", "source": "migration"}, now, embedding_provider)
                stats["facts"] += 1

    # interests, preferences, values, personality -> behavior trait (trend)
    for key in ["interests", "preferences", "values", "personality"]:
        items = kv_items.get(key)
        if items and isinstance(items, list):
            for item in items:
                if item and isinstance(item, str) and item.strip():
                    context = "general"
                    if key == "values":
                        context = "personal"
                    await _create_trait(session, user_id, f"用户{item}", "behavior", "trend", 0.2, context, now, embedding_provider)
                    stats["traits"] += 1

    # --- Emotion Profile -> trait ---
    ep_result = await session.execute(
        sql_text(
            "SELECT dominant_emotions, emotion_triggers, last_reflected_at "
            "FROM emotion_profiles WHERE user_id = :uid"
        ),
        {"uid": user_id},
    )
    ep_row = ep_result.first()

    if ep_row:
        # dominant_emotions -> trait
        if ep_row.dominant_emotions and isinstance(ep_row.dominant_emotions, dict):
            for emotion, weight in ep_row.dominant_emotions.items():
                if emotion and weight and float(weight) > 0.2:
                    content = f"用户经常表现出{emotion}情绪"
                    await _create_trait(session, user_id, content, "behavior", "trend", 0.25, "general", now, embedding_provider)
                    stats["traits"] += 1

        # emotion_triggers -> trait
        if ep_row.emotion_triggers and isinstance(ep_row.emotion_triggers, dict):
            for topic, trigger_data in ep_row.emotion_triggers.items():
                if topic and isinstance(trigger_data, dict):
                    valence = trigger_data.get("valence", 0)
                    label = "积极" if valence > 0.3 else "消极" if valence < -0.3 else "中性"
                    content = f"讨论{topic}话题时情绪偏{label}"
                    ctx = "work" if topic in ("工作", "work", "项目", "project") else "general"
                    await _create_trait(session, user_id, content, "behavior", "trend", 0.2, ctx, now, embedding_provider)
                    stats["traits"] += 1

        # watermark -> reflection_cycles
        if ep_row.last_reflected_at:
            await session.execute(
                sql_text(
                    "INSERT INTO reflection_cycles "
                    "(id, user_id, trigger_type, status, started_at, completed_at) "
                    "VALUES (:id, :uid, 'migration', 'completed', :ts, :ts)"
                ),
                {"id": str(uuid.uuid4()), "uid": user_id, "ts": ep_row.last_reflected_at},
            )
            stats["watermarks"] += 1

    # --- conversation_sessions watermark -> reflection_cycles ---
    cs_result = await session.execute(
        sql_text(
            "SELECT last_reflected_at FROM conversation_sessions "
            "WHERE user_id = :uid AND last_reflected_at IS NOT NULL "
            "ORDER BY last_reflected_at DESC LIMIT 1"
        ),
        {"uid": user_id},
    )
    cs_row = cs_result.first()
    if cs_row and cs_row.last_reflected_at:
        # 检查是否已有更新的 watermark（来自 emotion_profiles 迁移）
        existing = await session.execute(
            sql_text(
                "SELECT completed_at FROM reflection_cycles "
                "WHERE user_id = :uid AND status = 'completed' "
                "ORDER BY completed_at DESC LIMIT 1"
            ),
            {"uid": user_id},
        )
        existing_row = existing.first()
        if not existing_row or cs_row.last_reflected_at > existing_row.completed_at:
            await session.execute(
                sql_text(
                    "INSERT INTO reflection_cycles "
                    "(id, user_id, trigger_type, status, started_at, completed_at) "
                    "VALUES (:id, :uid, 'migration', 'completed', :ts, :ts)"
                ),
                {"id": str(uuid.uuid4()), "uid": user_id, "ts": cs_row.last_reflected_at},
            )
            stats["watermarks"] += 1

    # 清理 KV profile namespace
    await session.execute(
        sql_text("DELETE FROM key_values WHERE namespace = 'profile' AND scope_id = :uid"),
        {"uid": user_id},
    )

    logger.info("用户 %s 迁移完成: facts=%d traits=%d watermarks=%d", user_id, stats["facts"], stats["traits"], stats["watermarks"])
    return stats


async def _create_memory(session, user_id, content, memory_type, metadata, now, embedding_provider=None):
    """创建 Memory 行。"""
    content_hash = hashlib.md5(content.encode()).hexdigest()

    # 幂等性: 检查是否已存在相同 content_hash 的记忆
    existing = await session.execute(
        sql_text("SELECT id FROM memories WHERE user_id = :uid AND content_hash = :hash LIMIT 1"),
        {"uid": user_id, "hash": content_hash},
    )
    if existing.first():
        return

    # 生成 embedding
    embedding = None
    if embedding_provider:
        try:
            embedding = await embedding_provider.embed(content)
        except Exception as e:
            logger.warning("Embedding 生成失败，使用零向量: %s", e)

    if embedding is None:
        # 零向量占位
        from neuromem.models import _embedding_dims
        embedding = [0.0] * _embedding_dims

    vector_str = f"[{','.join(str(float(v)) for v in embedding)}]"

    await session.execute(
        sql_text(
            "INSERT INTO memories "
            "(id, user_id, content, embedding, memory_type, metadata, "
            " valid_from, content_hash, valid_at, created_at, updated_at) "
            "VALUES (:id, :uid, :content, :vec, :mtype, CAST(:meta AS jsonb), "
            " :now, :hash, :now, :now, :now)"
        ),
        {
            "id": str(uuid.uuid4()),
            "uid": user_id,
            "content": content,
            "vec": vector_str,
            "mtype": memory_type,
            "meta": __import__("json").dumps(metadata, ensure_ascii=False),
            "now": now,
            "hash": content_hash,
        },
    )


async def _create_trait(session, user_id, content, subtype, stage, confidence, context, now, embedding_provider=None):
    """创建 Trait Memory 行。"""
    content_hash = hashlib.md5(content.encode()).hexdigest()

    # 幂等性: 检查是否已存在相同 content_hash 的记忆
    existing = await session.execute(
        sql_text("SELECT id FROM memories WHERE user_id = :uid AND content_hash = :hash LIMIT 1"),
        {"uid": user_id, "hash": content_hash},
    )
    if existing.first():
        return

    embedding = None
    if embedding_provider:
        try:
            embedding = await embedding_provider.embed(content)
        except Exception as e:
            logger.warning("Embedding 生成失败，使用零向量: %s", e)

    if embedding is None:
        from neuromem.models import _embedding_dims
        embedding = [0.0] * _embedding_dims

    vector_str = f"[{','.join(str(float(v)) for v in embedding)}]"

    await session.execute(
        sql_text(
            "INSERT INTO memories "
            "(id, user_id, content, embedding, memory_type, metadata, "
            " trait_subtype, trait_stage, trait_confidence, trait_context, "
            " trait_first_observed, trait_window_start, trait_window_end, "
            " valid_from, content_hash, valid_at, created_at, updated_at) "
            "VALUES (:id, :uid, :content, :vec, 'trait', CAST(:meta AS jsonb), "
            " :subtype, :stage, :confidence, :context, "
            " :now, :now, :window_end, "
            " :now, :hash, :now, :now, :now)"
        ),
        {
            "id": str(uuid.uuid4()),
            "uid": user_id,
            "content": content,
            "vec": vector_str,
            "meta": __import__("json").dumps({"source": "migration", "evidence_ids": []}, ensure_ascii=False),
            "subtype": subtype,
            "stage": stage,
            "confidence": confidence,
            "context": context,
            "now": now,
            "hash": content_hash,
            "window_end": now + timedelta(days=30),
        },
    )


def main():
    parser = argparse.ArgumentParser(description="Profile 统一架构数据迁移")
    parser.add_argument("--database-url", required=True, help="PostgreSQL 连接字符串")
    parser.add_argument("--dry-run", action="store_true", help="预览变更，不提交")
    parser.add_argument("--embedding-api-key", help="Embedding API Key（可选，无则使用零向量）")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    # 可选：初始化 embedding provider
    embedding = None
    if args.embedding_api_key:
        try:
            from neuromem.providers.siliconflow import SiliconFlowEmbedding
            embedding = SiliconFlowEmbedding(api_key=args.embedding_api_key)
        except Exception as e:
            logger.warning("无法初始化 Embedding Provider: %s，将使用零向量", e)

    result = asyncio.run(migrate(args.database_url, dry_run=args.dry_run, embedding_provider=embedding))
    print(f"\n迁移结果: {result}")


if __name__ == "__main__":
    main()
