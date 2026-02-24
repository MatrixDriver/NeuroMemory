"""NeuroMemory main class (facade pattern)."""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from neuromemory.db import Database
from neuromemory.providers.embedding import EmbeddingProvider
from neuromemory.providers.llm import LLMProvider
from neuromemory.storage.base import ObjectStorage

logger = logging.getLogger(__name__)


@dataclass
class ExtractionStrategy:
    """Memory extraction trigger strategy.

    Controls when NeuroMemory automatically extracts structured memories
    (facts, episodes) from conversation messages using LLM.

    Inspired by AWS Bedrock AgentCore trigger conditions.

    Args:
        message_interval: Extract every N messages per session (0 = disabled).
        idle_timeout: Extract after N seconds of session inactivity (0 = disabled).
            Requires a running asyncio event loop (works in async apps,
            not effective during blocking input() calls).
        on_session_close: Extract when a session is explicitly closed via
            conversations.close_session().
        on_shutdown: Extract for all active sessions when NeuroMemory.close()
            is called.

    Examples:
        # Default: every 10 messages + 10 min idle + session close + shutdown
        ExtractionStrategy()

        # Only on session close and shutdown, no periodic extraction
        ExtractionStrategy(message_interval=0, idle_timeout=0)

        # Aggressive: every 5 messages, 2 min idle
        ExtractionStrategy(message_interval=5, idle_timeout=120)
    """

    message_interval: int = 10
    idle_timeout: float = 600
    on_session_close: bool = True
    on_shutdown: bool = True
    reflection_interval: int = 20  # Trigger reflection every N extractions (0 = disabled)


class KVFacade:
    """Key-value storage facade.

    user_id is used as scope_id internally to enforce user isolation.
    """

    def __init__(self, db: Database):
        self._db = db

    async def set(self, user_id: str, namespace: str, key: str, value):
        from neuromemory.services.kv import KVService
        async with self._db.session() as session:
            svc = KVService(session)
            return await svc.set(namespace, user_id, key, value)

    async def get(self, user_id: str, namespace: str, key: str):
        from neuromemory.services.kv import KVService
        async with self._db.session() as session:
            svc = KVService(session)
            return await svc.get(namespace, user_id, key)

    async def list(self, user_id: str, namespace: str, prefix: str | None = None, limit: int = 100):
        from neuromemory.services.kv import KVService
        async with self._db.session() as session:
            svc = KVService(session)
            return await svc.list(namespace, user_id, prefix, limit)

    async def delete(self, user_id: str, namespace: str, key: str) -> bool:
        from neuromemory.services.kv import KVService
        async with self._db.session() as session:
            svc = KVService(session)
            return await svc.delete(namespace, user_id, key)

    async def batch_set(self, user_id: str, namespace: str, items: dict):
        from neuromemory.services.kv import KVService
        async with self._db.session() as session:
            svc = KVService(session)
            return await svc.batch_set(namespace, user_id, items)


class ConversationsFacade:
    """Conversations facade."""

    def __init__(
        self,
        db: Database,
        _on_message_added=None,
        _on_session_closed=None,
        _on_extraction_done=None,
        _auto_extract: bool = True,
        _embedding: EmbeddingProvider | None = None,
        _llm: LLMProvider | None = None,
        _graph_enabled: bool = False,
    ):
        self._db = db
        self._on_message_added = _on_message_added
        self._on_session_closed = _on_session_closed
        self._on_extraction_done = _on_extraction_done
        self._auto_extract = _auto_extract
        self._embedding = _embedding
        self._llm = _llm
        self._graph_enabled = _graph_enabled

    async def add_message(self, user_id: str, role: str, content: str, session_id: str | None = None, metadata: dict | None = None):
        from neuromemory.services.conversation import ConversationService
        async with self._db.session() as session:
            svc = ConversationService(session)
            msg = await svc.add_message(user_id, role, content, session_id, metadata)

        # P1: Generate conversation embedding for recall (v0.2.0)
        # 🚀 优化：只对 user 消息计算 embedding，避免重复和浪费
        # AI 回复是对用户的响应，检索时会造成重复，且没有新信息
        if self._embedding and role == "user":
            asyncio.create_task(self._generate_conversation_embedding_async(msg))

        # Strategy-based extraction (old logic)
        if self._on_message_added:
            await self._on_message_added(user_id, msg.session_id, 1)

        # Auto-extract (new logic, like mem0)
        # 🚀 优化：只对 user 消息提取记忆，AI 回复不包含用户信息
        if self._auto_extract and self._llm and self._embedding and role == "user":
            asyncio.create_task(self._extract_single_message_async(user_id, msg.session_id, [msg]))

        return msg

    async def add_messages_batch(self, user_id: str, messages: list[dict], session_id: str | None = None):
        from neuromemory.services.conversation import ConversationService
        async with self._db.session() as session:
            svc = ConversationService(session)
            sid, ids = await svc.add_messages_batch(user_id, messages, session_id)

        # Strategy-based extraction (old logic)
        if self._on_message_added:
            await self._on_message_added(user_id, sid, len(messages))

        # Auto-extract (new logic, batch mode)
        if self._auto_extract and self._llm and self._embedding:
            # Get all messages in this session
            async with self._db.session() as session:
                svc = ConversationService(session)
                all_messages = await svc.get_session_messages(user_id, sid, limit=1000)
            await self._extract_batch(user_id, sid, all_messages)

        return sid, ids

    async def _generate_conversation_embedding(self, msg):
        """Generate and store embedding for conversation message (P1 feature).

        This enables recall to search both extracted memories and original conversations.
        """
        from sqlalchemy import update
        from neuromemory.models.conversation import Conversation
        try:
            embedding_vector = await self._embedding.embed(msg.content)
            async with self._db.session() as session:
                await session.execute(
                    update(Conversation)
                    .where(Conversation.id == msg.id)
                    .values(embedding=embedding_vector)
                )
                await session.commit()
            logger.debug(f"Generated conversation embedding for message {msg.id}")
        except Exception as e:
            logger.warning(f"Failed to generate conversation embedding: {e}")

    async def _generate_conversation_embedding_async(self, msg):
        """异步后台生成 conversation embedding，不阻塞主流程。

        所有异常都会被捕获并记录，不会影响对话响应。
        """
        try:
            await self._generate_conversation_embedding(msg)
        except Exception as e:
            # 在测试环境中，session 可能已经关闭，这是正常的
            from sqlalchemy.exc import IllegalStateChangeError
            if isinstance(e, IllegalStateChangeError) or "connection is closed" in str(e):
                logger.debug(f"后台 embedding 生成被中断（session 已关闭）: message_id={msg.id}")
            else:
                logger.error(f"后台 embedding 生成失败: message_id={msg.id}, error={e}", exc_info=True)

    async def _extract_single_message(self, user_id: str, session_id: str, messages: list):
        """Extract memories from a single message (auto-extract mode)."""
        from neuromemory.services.memory_extraction import MemoryExtractionService

        async with self._db.session() as session:
            extraction_svc = MemoryExtractionService(
                session,
                self._embedding,
                self._llm,
                graph_enabled=self._graph_enabled,
            )
            await extraction_svc.extract_from_messages(user_id, messages)

        logger.debug(f"Auto-extracted memories for {user_id} from single message")

        if self._on_extraction_done:
            asyncio.create_task(self._on_extraction_done(user_id))

    async def _extract_single_message_async(self, user_id: str, session_id: str, messages: list):
        """异步后台提取单条消息的记忆，不阻塞主流程。

        所有异常都会被捕获并记录，不会影响对话响应。
        """
        try:
            await self._extract_single_message(user_id, session_id, messages)
            if self._on_extraction_done:
                await self._on_extraction_done(user_id)
        except Exception as e:
            # 在测试环境中，session 可能已经关闭，这是正常的
            from sqlalchemy.exc import IllegalStateChangeError
            if isinstance(e, IllegalStateChangeError) or "connection is closed" in str(e):
                logger.debug(
                    f"后台记忆提取被中断（session 已关闭）: user_id={user_id}, session_id={session_id}"
                )
            else:
                logger.error(
                    f"后台记忆提取失败: user_id={user_id}, session_id={session_id}, error={e}",
                    exc_info=True
                )

    async def _extract_batch(self, user_id: str, session_id: str, messages: list):
        """Extract memories from a batch of messages (auto-extract mode)."""
        from neuromemory.services.memory_extraction import MemoryExtractionService

        async with self._db.session() as session:
            extraction_svc = MemoryExtractionService(
                session,
                self._embedding,
                self._llm,
                graph_enabled=self._graph_enabled,
            )
            result = await extraction_svc.extract_from_messages(user_id, messages)

        logger.info(
            f"Auto-extracted {result['facts_extracted']} facts, "
            f"{result['episodes_extracted']} episodes from batch for {user_id}"
        )
        if self._on_extraction_done:
            await self._on_extraction_done(user_id)

        if self._on_extraction_done:
            asyncio.create_task(self._on_extraction_done(user_id))

    async def close_session(self, user_id: str, session_id: str) -> None:
        """Close a conversation session, triggering memory extraction if configured."""
        if self._on_session_closed:
            await self._on_session_closed(user_id, session_id)

    async def get_session_messages(self, user_id: str, session_id: str, limit: int = 100, offset: int = 0):
        from neuromemory.services.conversation import ConversationService
        async with self._db.session() as session:
            svc = ConversationService(session)
            return await svc.get_session_messages(user_id, session_id, limit, offset)

    async def list_sessions(self, user_id: str, limit: int = 50, offset: int = 0):
        from neuromemory.services.conversation import ConversationService
        async with self._db.session() as session:
            svc = ConversationService(session)
            return await svc.list_sessions(user_id, limit, offset)

    async def get_unextracted_messages(self, user_id: str, session_id: str | None = None, limit: int = 100):
        from neuromemory.services.conversation import ConversationService
        async with self._db.session() as session:
            svc = ConversationService(session)
            return await svc.get_unextracted_messages(user_id, session_id, limit)


class FilesFacade:
    """Files facade."""

    def __init__(self, db: Database, embedding: EmbeddingProvider, storage: ObjectStorage):
        self._db = db
        self._embedding = embedding
        self._storage = storage

    async def upload(self, user_id: str, filename: str, file_data: bytes, category: str = "general", tags: list[str] | None = None, metadata: dict | None = None):
        from neuromemory.services.files import FileService
        async with self._db.session() as session:
            svc = FileService(session, self._embedding, self._storage)
            return await svc.upload(user_id, filename, file_data, category, tags, metadata)

    async def create_from_text(self, user_id: str, title: str, content: str, category: str = "general", tags: list[str] | None = None, metadata: dict | None = None):
        from neuromemory.services.files import FileService
        async with self._db.session() as session:
            svc = FileService(session, self._embedding, self._storage)
            return await svc.create_from_text(user_id, title, content, category, tags, metadata)

    async def list(self, user_id: str, category: str | None = None, tags: list[str] | None = None, file_types: list[str] | None = None, limit: int = 50):
        from neuromemory.services.files import FileService
        async with self._db.session() as session:
            svc = FileService(session, self._embedding, self._storage)
            return await svc.list_documents(user_id, category, tags, file_types, limit)

    async def search(self, user_id: str, query: str, limit: int = 5, file_types: list[str] | None = None, category: str | None = None, tags: list[str] | None = None) -> list[dict]:
        from neuromemory.services.files import FileService
        async with self._db.session() as session:
            svc = FileService(session, self._embedding, self._storage)
            return await svc.search(user_id, query, limit, file_types, category, tags)

    async def get(self, user_id: str, file_id):
        from neuromemory.services.files import FileService
        async with self._db.session() as session:
            svc = FileService(session, self._embedding, self._storage)
            return await svc.get_document(file_id, user_id)

    async def delete(self, user_id: str, file_id) -> bool:
        from neuromemory.services.files import FileService
        async with self._db.session() as session:
            svc = FileService(session, self._embedding, self._storage)
            return await svc.delete_document(file_id, user_id)


class GraphFacade:
    """Graph facade."""

    def __init__(self, db: Database):
        self._db = db

    async def create_node(self, node_type, node_id: str, properties: dict | None = None, user_id: str | None = None):
        from neuromemory.services.graph import GraphService
        async with self._db.session() as session:
            svc = GraphService(session)
            return await svc.create_node(node_type, node_id, properties, user_id)

    async def get_node(self, user_id: str, node_type, node_id: str):
        from neuromemory.services.graph import GraphService
        async with self._db.session() as session:
            svc = GraphService(session)
            return await svc.get_node(node_type, node_id, user_id)

    async def update_node(self, user_id: str, node_type, node_id: str, properties: dict):
        from neuromemory.services.graph import GraphService
        async with self._db.session() as session:
            svc = GraphService(session)
            return await svc.update_node(node_type, node_id, properties, user_id)

    async def delete_node(self, user_id: str, node_type, node_id: str):
        from neuromemory.services.graph import GraphService
        async with self._db.session() as session:
            svc = GraphService(session)
            return await svc.delete_node(node_type, node_id, user_id)

    async def create_edge(self, source_type, source_id: str, edge_type, target_type, target_id: str, properties: dict | None = None, user_id: str | None = None):
        from neuromemory.services.graph import GraphService
        async with self._db.session() as session:
            svc = GraphService(session)
            return await svc.create_edge(source_type, source_id, edge_type, target_type, target_id, properties, user_id)

    async def get_neighbors(self, user_id: str, node_type, node_id: str, edge_types=None, direction: str = "both", limit: int = 10):
        from neuromemory.services.graph import GraphService
        async with self._db.session() as session:
            svc = GraphService(session)
            return await svc.get_neighbors(node_type, node_id, edge_types, direction, limit, user_id)

    async def find_path(self, user_id: str, source_type, source_id: str, target_type, target_id: str, max_depth: int = 3):
        from neuromemory.services.graph import GraphService
        async with self._db.session() as session:
            svc = GraphService(session)
            return await svc.find_path(source_type, source_id, target_type, target_id, max_depth, user_id)


class NeuroMemory:
    """Main NeuroMemory facade - entry point for all operations.

    Args:
        database_url: PostgreSQL connection string
        embedding: Embedding provider (SiliconFlow/OpenAI/SentenceTransformer)
        llm: LLM provider (required, for memory extraction and reflection)
        storage: Optional object storage (for files)
        extraction: Optional extraction strategy (for interval-based extraction)
        auto_extract: If True, automatically extract memories on add_message (default: True, like mem0)
        graph_enabled: Enable graph memory storage
        pool_size: Database connection pool size
        echo: Enable SQLAlchemy SQL logging
        reflection_interval: In auto_extract mode, trigger background reflect every N extractions
            (0 = disabled). Requires llm. E.g. reflection_interval=10 runs reflect after every
            10 messages. reflect() runs fully in the background and never blocks add_message.

    Usage:
        # Auto-extract mode (default, like mem0)
        async with NeuroMemory(
            database_url="postgresql+asyncpg://...",
            embedding=SiliconFlowEmbedding(api_key="..."),
            llm=OpenAILLM(api_key="..."),
            auto_extract=True,  # Default
        ) as nm:
            # Memories are extracted immediately
            await nm.conversations.add_message(user_id="alice", role="user", content="I work at Google")
            # → facts/preferences/episodes automatically extracted and stored

        # Strategy-based extraction (interval-based)
        async with NeuroMemory(
            ...,
            auto_extract=False,
            extraction=ExtractionStrategy(message_interval=10),
        ) as nm:
            # Memories extracted every 10 messages
            await nm.conversations.add_message(...)
    """

    def __init__(
        self,
        database_url: str,
        embedding: EmbeddingProvider,
        llm: LLMProvider,
        storage: Optional[ObjectStorage] = None,
        extraction: Optional[ExtractionStrategy] = None,
        auto_extract: bool = True,
        graph_enabled: bool = False,
        pool_size: int = 10,
        echo: bool = False,
        reflection_interval: int = 20,
    ):
        """
        Args:
            reflection_interval: Trigger background reflect() every N user messages per user.
                Default 20: runs reflect in the background after every 20 user messages.
                0 = disabled. Never blocks add_message(). Requires llm.
        """
        # Set embedding dimensions before any model import
        import neuromemory.models as _models
        _models._embedding_dims = embedding.dims

        self._db = Database(database_url, pool_size=pool_size, echo=echo)
        self._embedding = embedding
        self._llm = llm
        self._storage = storage
        self._extraction = extraction
        self._auto_extract = auto_extract
        self._graph_enabled = graph_enabled
        self._reflection_interval = reflection_interval

        # Extraction state tracking
        self._msg_counts: dict[tuple[str, str], int] = {}
        self._idle_tasks: dict[tuple[str, str], asyncio.Task] = {}
        self._active_sessions: set[tuple[str, str]] = set()
        self._extraction_counts: dict[str, int] = {}  # user_id -> count (ExtractionStrategy mode)
        self._reflect_counts: dict[str, int] = {}      # user_id -> count (reflection_interval mode)
        self._bg_tasks: list[asyncio.Task] = []        # background reflect tasks (awaited on close)

        # Embedding cache for query deduplication (reduces API calls)
        self._embedding_cache: OrderedDict[str, list[float]] = OrderedDict()
        self._embedding_cache_max_size = 100  # True LRU

        # Set up callbacks if extraction is configured and LLM is available
        _has_extraction = bool(extraction and llm)
        on_msg = self._on_message_added if _has_extraction else None
        on_close = self._on_session_closed if _has_extraction else None
        on_extraction_done = (
            self._maybe_trigger_reflect
            if reflection_interval > 0 and llm
            else None
        )

        # Sub-module facades
        self.kv = KVFacade(self._db)
        self.conversations = ConversationsFacade(
            self._db,
            _on_message_added=on_msg,
            _on_session_closed=on_close,
            _on_extraction_done=on_extraction_done,
            _auto_extract=auto_extract,
            _embedding=embedding,
            _llm=llm,
            _graph_enabled=graph_enabled,
        )
        self.graph = GraphFacade(self._db)

        if storage:
            self.files = FilesFacade(self._db, self._embedding, storage)

    async def init(self) -> None:
        """Initialize database tables and optional storage."""
        await self._db.init()
        if self._storage:
            await self._storage.init()

    async def close(self) -> None:
        """Close database connections. Triggers extraction if on_shutdown is set."""
        # Cancel idle timers
        for task in self._idle_tasks.values():
            task.cancel()
        self._idle_tasks.clear()

        # Extract on shutdown for all active sessions
        if self._extraction and self._extraction.on_shutdown and self._llm:
            for user_id, session_id in self._active_sessions:
                await self._do_extraction(user_id, session_id)
        self._active_sessions.clear()
        self._msg_counts.clear()

        # Await all pending background reflect tasks before closing DB
        pending = [t for t in self._bg_tasks if not t.done()]
        if pending:
            logger.debug("Waiting for %d background reflect task(s) to complete", len(pending))
            await asyncio.gather(*pending, return_exceptions=True)
        self._bg_tasks.clear()

        await self._db.close()

    async def __aenter__(self) -> "NeuroMemory":
        await self.init()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    # -- Embedding cache methods --

    async def _cached_embed(self, text: str) -> list[float]:
        """Cache-aware embedding computation.

        Uses an in-memory LRU-style cache to avoid redundant API calls
        for the same query text within a session.

        Args:
            text: Text to embed

        Returns:
            Embedding vector (list of floats)
        """
        if text in self._embedding_cache:
            # Move to end = mark as recently used
            self._embedding_cache.move_to_end(text)
            logger.debug(f"Embedding cache hit for text length {len(text)}")
            return self._embedding_cache[text]

        embedding = await self._embedding.embed(text)

        # True LRU: insert at end, evict from front (least recently used)
        self._embedding_cache[text] = embedding
        if len(self._embedding_cache) > self._embedding_cache_max_size:
            self._embedding_cache.popitem(last=False)
            logger.debug("Evicted LRU embedding from cache")

        logger.debug(f"Cached embedding for text length {len(text)}")
        return embedding

    def clear_embedding_cache(self) -> None:
        """Clear the embedding cache. Useful for testing or memory management."""
        self._embedding_cache.clear()
        logger.info("Embedding cache cleared")

    # -- Auto-extraction internals --

    async def _on_session_closed(self, user_id: str, session_id: str) -> None:
        """Callback invoked when a conversation session is closed."""
        key = (user_id, session_id)

        # Cancel idle timer for this session
        old_task = self._idle_tasks.pop(key, None)
        if old_task:
            old_task.cancel()

        # Extract if on_session_close is enabled
        if self._extraction.on_session_close:
            await self._do_extraction(user_id, session_id)

        # Clean up tracking state
        self._active_sessions.discard(key)
        self._msg_counts.pop(key, None)

    async def _on_message_added(self, user_id: str, session_id: str, count: int) -> None:
        """Callback invoked after conversation messages are saved."""
        key = (user_id, session_id)
        self._active_sessions.add(key)

        # Message interval trigger
        if self._extraction.message_interval > 0:
            self._msg_counts[key] = self._msg_counts.get(key, 0) + count
            if self._msg_counts[key] >= self._extraction.message_interval:
                await self._do_extraction(user_id, session_id)
                self._msg_counts[key] = 0

        # Idle timeout trigger - reset timer
        if self._extraction.idle_timeout > 0:
            old_task = self._idle_tasks.pop(key, None)
            if old_task:
                old_task.cancel()
            self._idle_tasks[key] = asyncio.create_task(
                self._idle_extraction_timer(user_id, session_id)
            )

    async def _idle_extraction_timer(self, user_id: str, session_id: str) -> None:
        """Wait for idle timeout then trigger extraction."""
        try:
            await asyncio.sleep(self._extraction.idle_timeout)
            await self._do_extraction(user_id, session_id)
        except asyncio.CancelledError:
            pass

    async def _maybe_trigger_reflect(self, user_id: str) -> None:
        """Called after each user message extraction; triggers background reflect every N messages."""
        self._reflect_counts[user_id] = self._reflect_counts.get(user_id, 0) + 1
        if self._reflect_counts[user_id] >= self._reflection_interval:
            self._reflect_counts[user_id] = 0
            logger.info(
                "Auto-reflect triggered for user=%s (interval=%d)",
                user_id, self._reflection_interval,
            )
            await self.reflect(user_id, background=True)

    async def _do_extraction(self, user_id: str, session_id: str) -> None:
        """Extract memories from unprocessed messages in a session."""
        try:
            messages = await self.conversations.get_unextracted_messages(
                user_id, session_id,
            )
            if not messages:
                return
            stats = await self._extract_memories(user_id, messages)
            logger.info(
                "Auto-extracted memories: user=%s session=%s "
                "facts=%d episodes=%d msgs=%d",
                user_id, session_id,
                stats["facts_extracted"],
                stats["episodes_extracted"],
                stats["messages_processed"],
            )

            # Check if reflection should be triggered
            if (
                self._extraction
                and self._extraction.reflection_interval > 0
                and self._llm
            ):
                self._extraction_counts[user_id] = (
                    self._extraction_counts.get(user_id, 0) + 1
                )
                if self._extraction_counts[user_id] >= self._extraction.reflection_interval:
                    self._extraction_counts[user_id] = 0
                    # 后台异步执行 reflect，不阻塞当前对话流程
                    await self.reflect(user_id, background=True)

        except Exception as e:
            logger.error("Auto-extraction failed: user=%s session=%s error=%s",
                         user_id, session_id, e, exc_info=True)

    # -- Top-level convenience methods --

    async def _add_memory(
        self,
        user_id: str,
        content: str,
        memory_type: str = "general",
        metadata: dict | None = None,
        check_conflict: bool = True,
    ):
        """Add a memory with auto-generated embedding (internal).

        Args:
            check_conflict: For fact-type memories, detect contradicting
                existing facts (cosine similarity > 0.85) and version them.
                Defaults to True.
        """
        from datetime import timezone
        from neuromemory.services.search import SearchService

        async with self._db.session() as session:
            svc = SearchService(session, self._embedding, self._db.pg_search_available)
            record = await svc.add_memory(user_id, content, memory_type, metadata)

            # Conflict detection for fact-type memories
            if check_conflict and memory_type == "fact" and self._embedding:
                await self._check_memory_conflict(session, user_id, content, record)

            return record

    async def get_memories_by_time_range(self, user_id: str, start_time, end_time=None, memory_type=None, limit=100, offset=0):
        from neuromemory.services.memory import MemoryService
        async with self._db.session() as session:
            svc = MemoryService(session)
            return await svc.get_memories_by_time_range(user_id, start_time, end_time, memory_type, limit, offset)

    async def get_recent_memories(self, user_id: str, days: int = 7, memory_types=None, limit: int = 50):
        from neuromemory.services.memory import MemoryService
        async with self._db.session() as session:
            svc = MemoryService(session)
            return await svc.get_recent_memories(user_id, days, memory_types, limit)

    async def _extract_memories(self, user_id: str, messages):
        """Extract memories from conversation messages using LLM (internal)."""
        from neuromemory.services.conversation import ConversationService
        from neuromemory.services.memory_extraction import MemoryExtractionService
        async with self._db.session() as session:
            svc = MemoryExtractionService(
                session, self._embedding, self._llm,
                graph_enabled=self._graph_enabled,
            )
            result = await svc.extract_from_messages(user_id, messages)
            # Mark messages as extracted so they won't be re-processed
            msg_ids = [m.id for m in messages if hasattr(m, "id")]
            if msg_ids:
                conv_svc = ConversationService(session)
                await conv_svc.mark_messages_extracted(msg_ids)
            return result

    async def recall(
        self,
        user_id: str,
        query: str,
        limit: int = 20,
        decay_rate: float | None = None,
        memory_type: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        event_after: datetime | None = None,
        event_before: datetime | None = None,
        include_conversations: bool = False,
        as_of: datetime | None = None,
    ) -> dict:
        """Hybrid recall: memories + graph, merged and deduplicated.

        Args:
            user_id: The user to recall memories for.
            query: Natural language query.
            limit: Max number of merged results to return.
            decay_rate: Time-decay factor for recency scoring.
            memory_type: Filter by memory type (e.g. "fact", "episodic").
            created_after: Filter by created_at >= this datetime.
            created_before: Filter by created_at <= this datetime.
            event_after: Filter by extracted_timestamp >= this datetime.
                Overrides auto-extracted time range from query.
            event_before: Filter by extracted_timestamp <= this datetime.
                Overrides auto-extracted time range from query.
            include_conversations: If True, also search raw conversation
                fragments and include them in the result (adds latency).
                Defaults to False — extracted memories are preferred.
            as_of: Time-travel query — recall memories valid at this point
                in time. When None (default), only returns currently valid
                memories. Must be a timezone-aware datetime.

        Returns:
            {
                "vector_results": [...],       # extracted memories
                "conversation_results": [...], # raw conversations (only if include_conversations=True)
                "graph_results": [...],        # graph entities
                "merged": [...],               # deduplicated merge
            }
        """
        from neuromemory.services.search import DEFAULT_DECAY_RATE
        from neuromemory.services.temporal import TemporalExtractor

        # Compute query embedding once, reuse for all parallel searches
        query_embedding = await self._cached_embed(query)

        # Auto-extract time range from query, then let explicit args override
        temporal = TemporalExtractor()
        auto_after, auto_before = temporal.extract_time_range(query)
        _event_after = event_after if event_after is not None else auto_after
        _event_before = event_before if event_before is not None else auto_before
        _decay = decay_rate or DEFAULT_DECAY_RATE

        # Parallel fetch: memories + profile (+ conversations + graph if enabled)
        coros = [
            self._fetch_vector_memories(
                user_id, query, limit, query_embedding, _event_after, _event_before, _decay,
                as_of=as_of,
                memory_type=memory_type,
                created_after=created_after,
                created_before=created_before,
            ),
            self._fetch_user_profile(user_id),
        ]
        conv_idx: int | None = None
        graph_idx: int | None = None
        if include_conversations:
            conv_idx = len(coros)
            coros.append(self._search_conversations(user_id, query, limit, query_embedding=query_embedding))
        if self._graph_enabled:
            graph_idx = len(coros)
            coros.append(self._fetch_graph_memories(user_id, query, limit, as_of=as_of))

        results = await asyncio.gather(*coros, return_exceptions=True)

        vector_results: list[dict] = results[0] if not isinstance(results[0], Exception) else []
        user_profile: dict = results[1] if not isinstance(results[1], Exception) else {}
        conversation_results: list[dict] = (
            results[conv_idx] if conv_idx is not None and not isinstance(results[conv_idx], Exception) else []
        )
        graph_results: list[dict] = []
        if self._graph_enabled and graph_idx is not None:
            raw = results[graph_idx]
            if isinstance(raw, Exception):
                logger.warning(f"Graph search failed: {raw}")
            else:
                graph_results = raw

        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.warning("recall fetch[%d] failed: %s", i, r)

        # Build graph triples for coverage boost
        graph_triples = [
            (t.get("subject", "").lower(), t.get("relation", ""), t.get("object", "").lower())
            for t in graph_results
            if t.get("subject") and t.get("object")
        ]

        # Deduplicate by content
        seen_contents: set[str] = set()
        merged: list[dict] = []

        for r in vector_results:
            content = r.get("content", "")
            if content not in seen_contents:
                seen_contents.add(content)
                entry = {**r, "source": "vector"}
                # Enrich content with metadata for LLM context
                ts = r.get("extracted_timestamp")
                ts_str = (ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]) if ts else None
                meta = r.get("metadata") or {}
                emotion = meta.get("emotion") if isinstance(meta, dict) else None
                sentiment_str = None
                if emotion and isinstance(emotion, dict):
                    label = emotion.get("label", "")
                    valence = emotion.get("valence")
                    if label:
                        sentiment_str = f"sentiment: {label}"
                    elif valence is not None:
                        tone = "positive" if valence > 0.2 else "negative" if valence < -0.2 else "neutral"
                        sentiment_str = f"sentiment: {tone}"

                if r.get("memory_type") == "episodic":
                    # Episodic format: "YYYY-MM-DD: content. sentiment: X"
                    if ts_str:
                        entry["content"] = f"{ts_str}: {content}" + (f". {sentiment_str}" if sentiment_str else "")
                    elif sentiment_str:
                        entry["content"] = f"{content}. {sentiment_str}"
                else:
                    # Facts/insights: timeless attributes, no date prefix needed
                    if sentiment_str:
                        entry["content"] = f"{content}. {sentiment_str}"

                # Graph triple coverage boost
                if graph_triples:
                    boost = 1.0
                    content_lower = content.lower()
                    for subj, _rel, obj in graph_triples:
                        subj_in = subj in content_lower
                        obj_in = obj in content_lower
                        if subj_in and obj_in:
                            boost += 0.5
                        elif subj_in or obj_in:
                            boost += 0.2
                    boost = min(boost, 2.0)
                    if r.get("score") is not None:
                        entry["score"] = round(r["score"] * boost, 4)
                    entry["graph_boost"] = round(boost, 2)

                merged.append(entry)

        # Merge conversation results when explicitly requested
        if include_conversations:
            for r in conversation_results:
                content = r.get("content", "")
                if content and content not in seen_contents:
                    seen_contents.add(content)
                    merged.append({**r, "source": "conversation"})

        # Graph triples participate in unified ranking
        for triple in graph_results:
            subj = triple.get("subject", "")
            rel = triple.get("relation", "")
            obj = triple.get("object", "")
            triple_content = f"{subj} → {rel} → {obj}"
            if triple_content not in seen_contents:
                seen_contents.add(triple_content)
                base_score = float(triple.get("confidence", 0.5))
                merged.append({
                    "content": triple_content,
                    "score": round(base_score, 4),
                    "source": "graph",
                    "memory_type": "graph_fact",
                })

        # Sort by score descending for unified ranking
        merged.sort(key=lambda x: x.get("score", 0), reverse=True)

        graph_context: list[str] = [
            f"{r.get('subject')} → {r.get('relation')} → {r.get('object')}"
            for r in graph_results
            if r.get("subject") and r.get("relation") and r.get("object")
        ]

        return {
            "vector_results": vector_results,
            "conversation_results": conversation_results,
            "graph_results": graph_results,
            "graph_context": graph_context,
            "user_profile": user_profile,
            "merged": merged[:limit],
        }

    async def _search_conversations(
        self,
        user_id: str,
        query: str,
        limit: int = 10,
        query_embedding: list[float] | None = None,
    ) -> list[dict]:
        """Search original conversation fragments (P1 feature).

        This preserves temporal details, dates, and specific information that
        may be lost during LLM extraction.

        Args:
            query_embedding: Optional pre-computed embedding to avoid recomputation
        """
        from sqlalchemy import text

        try:
            if query_embedding is None:
                query_embedding = await self._cached_embed(query)
            else:
                logger.debug("Using provided query_embedding, skipping embed call")
        except Exception as e:
            logger.warning(f"Failed to generate query embedding for conversations: {e}")
            return []

        # Convert query_embedding to pgvector string format
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in query_embedding):
            logger.warning("Invalid vector data: must contain only numeric values")
            return []

        vector_str = f"[{','.join(str(float(v)) for v in query_embedding)}]"

        async with self._db.session() as session:
            # Vector similarity search on conversations using raw SQL
            # Note: vector_str must be interpolated, not bound as parameter
            sql = text(
                f"""
                SELECT id, content, role, session_id, created_at, metadata,
                       1 - (embedding <=> '{vector_str}'::vector) AS similarity
                FROM conversations
                WHERE user_id = :user_id
                  AND embedding IS NOT NULL
                ORDER BY embedding <=> '{vector_str}'::vector
                LIMIT :limit
            """
            )

            result = await session.execute(sql, {"user_id": user_id, "limit": limit})
            rows = result.fetchall()

            conversations = []
            for row in rows:
                conversations.append({
                    "id": str(row.id),
                    "content": row.content,
                    "role": row.role,
                    "session_id": row.session_id,
                    "created_at": row.created_at,
                    "metadata": row.metadata or {},
                    "similarity": round(float(row.similarity), 4),
                })

            return conversations

    # -- Parallel recall helpers --

    async def _fetch_vector_memories(
        self,
        user_id: str,
        query: str,
        limit: int,
        query_embedding: list[float],
        event_after,
        event_before,
        decay_rate: float,
        as_of: datetime | None = None,
        memory_type: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> list[dict]:
        """Search extracted memories (vector + BM25 hybrid).

        When memory_type is specified, skips the episodic/fact split and
        searches with that type directly. Otherwise, for temporal queries,
        runs episodic and fact searches in parallel.
        """
        from neuromemory.services.search import SearchService

        common_kwargs = dict(
            decay_rate=decay_rate,
            query_embedding=query_embedding,
            as_of=as_of,
            created_after=created_after,
            created_before=created_before,
        )

        # User explicitly specified memory_type → single search
        if memory_type:
            async with self._db.session() as session:
                svc = SearchService(session, self._embedding, self._db.pg_search_available)
                return await svc.scored_search(
                    user_id, query, limit,
                    memory_type=memory_type,
                    event_after=event_after,
                    event_before=event_before,
                    **common_kwargs,
                )

        if event_after or event_before:
            # Two sub-searches in parallel using separate sessions
            async def _episodic():
                async with self._db.session() as s:
                    svc = SearchService(s, self._embedding, self._db.pg_search_available)
                    return await svc.scored_search(
                        user_id, query, limit,
                        memory_type="episodic",
                        event_after=event_after,
                        event_before=event_before,
                        **common_kwargs,
                    )

            async def _facts():
                async with self._db.session() as s:
                    svc = SearchService(s, self._embedding, self._db.pg_search_available)
                    return await svc.scored_search(
                        user_id, query, limit,
                        exclude_types=["episodic"],
                        **common_kwargs,
                    )

            episodic_results, fact_results = await asyncio.gather(_episodic(), _facts())
            seen_ids = {r["id"] for r in episodic_results}
            merged = list(episodic_results)
            for r in fact_results:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    merged.append(r)
            return merged[:limit]
        else:
            async with self._db.session() as session:
                svc = SearchService(session, self._embedding, self._db.pg_search_available)
                return await svc.scored_search(
                    user_id, query, limit,
                    **common_kwargs,
                )

    async def _fetch_user_profile(self, user_id: str) -> dict:
        """Read user profile from KV store in a single batch query."""
        try:
            from neuromemory.services.kv import KVService
            _profile_keys = {
                "identity", "occupation", "interests", "preferences",
                "values", "relationships", "personality",
            }
            async with self._db.session() as session:
                kv_svc = KVService(session)
                items = await kv_svc.list("profile", user_id)
                return {
                    item.key: item.value
                    for item in items
                    if item.key in _profile_keys and item.value
                }
        except Exception as e:
            logger.warning(f"Failed to read user profile: {e}")
            return {}

    async def _fetch_graph_memories(
        self, user_id: str, query: str, limit: int,
        as_of: datetime | None = None,
    ) -> list[dict]:
        """Graph entity recall with SQL-pushed substring matching."""
        from sqlalchemy import text as sql_text
        from neuromemory.services.graph_memory import GraphMemoryService

        query_lower = query.lower()
        async with self._db.session() as session:
            result = await session.execute(
                sql_text(
                    "SELECT DISTINCT node_id FROM graph_nodes "
                    "WHERE user_id = :uid "
                    "  AND node_id != 'user' "
                    "  AND length(node_id) > 1 "
                    "  AND strpos(:ql, node_id) > 0"
                ),
                {"uid": user_id, "ql": query_lower},
            )
            matched_entities = [row.node_id for row in result.fetchall()]

        matched_entities.append(user_id)
        logger.debug("Graph entity match: query=%s matched=%s", query[:50], matched_entities)

        async with self._db.session() as session:
            graph_svc = GraphMemoryService(session)
            seen_triples: set[str] = set()
            graph_results: list[dict] = []
            for entity in matched_entities:
                for f in await graph_svc.find_entity_facts(user_id, entity, limit, as_of=as_of):
                    key = f"{f.get('subject')}|{f.get('relation')}|{f.get('object')}"
                    if key not in seen_triples:
                        seen_triples.add(key)
                        graph_results.append(f)
        return graph_results

    async def _check_memory_conflict(
        self, session, user_id: str, content: str, new_record,
    ) -> None:
        """Detect contradicting fact memories and version them.

        If cosine similarity > 0.85 with an existing fact, the old memory
        gets valid_until set and superseded_by pointing to the new one.
        """
        from datetime import timezone
        from sqlalchemy import text as sql_text

        try:
            query_vector = await self._embedding.embed(content)
            vector_str = f"[{','.join(str(float(v)) for v in query_vector)}]"

            result = await session.execute(
                sql_text(f"""
                    SELECT id, content, version,
                           1 - (embedding <=> '{vector_str}'::vector) AS similarity
                    FROM embeddings
                    WHERE user_id = :uid
                      AND memory_type = 'fact'
                      AND valid_until IS NULL
                      AND id != :new_id
                    ORDER BY embedding <=> '{vector_str}'::vector
                    LIMIT 3
                """),
                {"uid": user_id, "new_id": new_record.id},
            )
            rows = result.fetchall()

            now = datetime.now(timezone.utc)
            max_version = 1
            for row in rows:
                if float(row.similarity) > 0.85 and row.content != content:
                    # Supersede the old memory
                    await session.execute(
                        sql_text("""
                            UPDATE embeddings
                            SET valid_until = :now, superseded_by = :new_id
                            WHERE id = :old_id
                        """),
                        {"now": now, "new_id": new_record.id, "old_id": row.id},
                    )
                    if row.version >= max_version:
                        max_version = row.version + 1
                    logger.info(
                        "Memory conflict: '%s' superseded by '%s'",
                        row.content[:50], content[:50],
                    )

            if max_version > 1:
                await session.execute(
                    sql_text("UPDATE embeddings SET version = :ver WHERE id = :id"),
                    {"ver": max_version, "id": new_record.id},
                )
        except Exception as e:
            logger.warning("Memory conflict check failed: %s", e)

    async def reflect(
        self,
        user_id: str,
        batch_size: int = 50,
        background: bool = False,
    ) -> dict | None:
        """Generate insights and update emotion profile from un-reflected memories.

        Uses a watermark (``last_reflected_at`` on EmotionProfile) to only
        process memories that haven't been analyzed yet.  Internally paginates
        through the new memories in batches so the LLM context stays bounded.

        First call: processes all memories.  Subsequent calls: only new ones.

        Args:
            user_id: The user to reflect about.
            batch_size: Number of memories per LLM call.
            background: If True, run in background via asyncio.create_task()
                        and return immediately with None.

        Returns:
            Result dict when background=False; None when background=True.
        """
        if background:
            async def _safe_reflect():
                try:
                    await self._reflect_impl(user_id, batch_size)
                except Exception as e:
                    logger.error("Background reflect failed: user=%s error=%s", user_id, e)
            task = asyncio.create_task(_safe_reflect())
            self._bg_tasks.append(task)
            return None
        return await self._reflect_impl(user_id, batch_size)

    async def _reflect_impl(
        self,
        user_id: str,
        batch_size: int = 50,
    ) -> dict:
        """Internal implementation of reflect()."""
        from neuromemory.services.reflection import ReflectionService
        from sqlalchemy import text as sql_text

        # --- Read watermark ---
        watermark = None
        async with self._db.session() as session:
            row = (await session.execute(
                sql_text("SELECT last_reflected_at FROM emotion_profiles WHERE user_id = :uid"),
                {"uid": user_id},
            )).first()
            if row and row.last_reflected_at:
                watermark = row.last_reflected_at

        # --- Count un-reflected memories (cheap) ---
        async with self._db.session() as session:
            where = "user_id = :uid AND memory_type != 'insight'"
            params: dict = {"uid": user_id}
            if watermark:
                where += " AND created_at > :wm"
                params["wm"] = watermark
            cnt = (await session.execute(
                sql_text(f"SELECT COUNT(*) FROM embeddings WHERE {where}"), params,
            )).scalar() or 0

        if cnt == 0:
            return {
                "memories_analyzed": 0,
                "insights_generated": 0,
                "insights": [],
                "emotion_profile": None,
            }

        # --- Seed existing insights for dedup ---
        existing_insights: list[dict] = []
        async with self._db.session() as session:
            result = await session.execute(
                sql_text("""
                    SELECT content, metadata FROM embeddings
                    WHERE user_id = :uid AND memory_type = 'insight'
                    ORDER BY created_at DESC LIMIT 50
                """),
                {"uid": user_id},
            )
            existing_insights = [
                {"content": r.content, "metadata": r.metadata}
                for r in result.fetchall()
            ]

        # --- Paginate through un-reflected memories ---
        all_insights: list[dict] = []
        total_analyzed = 0
        offset = 0
        emotion_profile = None
        max_created_at = watermark  # track new watermark

        while True:
            batch: list[dict] = []
            async with self._db.session() as session:
                where = "user_id = :uid AND memory_type != 'insight'"
                params = {"uid": user_id, "lim": batch_size, "off": offset}
                if watermark:
                    where += " AND created_at > :wm"
                    params["wm"] = watermark
                result = await session.execute(
                    sql_text(f"""
                        SELECT id, content, memory_type, metadata, created_at
                        FROM embeddings WHERE {where}
                        ORDER BY created_at ASC
                        LIMIT :lim OFFSET :off
                    """),
                    params,
                )
                for row in result.fetchall():
                    batch.append({
                        "id": str(row.id),
                        "content": row.content,
                        "memory_type": row.memory_type,
                        "metadata": row.metadata,
                        "created_at": row.created_at,
                    })
                    if max_created_at is None or row.created_at > max_created_at:
                        max_created_at = row.created_at

            if not batch:
                break

            total_analyzed += len(batch)

            async with self._db.session() as session:
                svc = ReflectionService(session, self._embedding, self._llm)
                batch_result = await svc.reflect(
                    user_id, batch, existing_insights or None,
                )

            batch_insights = batch_result.get("insights", [])
            all_insights.extend(batch_insights)
            for ins in batch_insights:
                existing_insights.append({
                    "content": ins.get("content", ""),
                    "metadata": {"category": ins.get("category", "pattern")},
                })

            if emotion_profile is None:
                emotion_profile = batch_result.get("emotion_profile")

            logger.info(
                "Reflect[%s] batch offset=%d: analyzed=%d insights=%d (total=%d/%d)",
                user_id, offset, len(batch), len(batch_insights), len(all_insights), cnt,
            )

            if len(batch) < batch_size:
                break
            offset += batch_size

        # --- Advance watermark ---
        if max_created_at is not None:
            async with self._db.session() as session:
                await session.execute(
                    sql_text("""
                        INSERT INTO emotion_profiles (user_id, last_reflected_at)
                        VALUES (:uid, :ts)
                        ON CONFLICT (user_id) DO UPDATE
                            SET last_reflected_at = EXCLUDED.last_reflected_at
                    """),
                    {"uid": user_id, "ts": max_created_at},
                )
                await session.commit()

        return {
            "memories_analyzed": total_analyzed,
            "insights_generated": len(all_insights),
            "insights": all_insights,
            "emotion_profile": emotion_profile,
        }

    # -- Time-travel APIs --

    async def rollback_memories(self, user_id: str, to_time: datetime) -> dict:
        """Rollback memories to a point in time.

        Invalidates all memories created after to_time, and reactivates
        their predecessors (if any were superseded).

        Args:
            user_id: User ID.
            to_time: Rollback to this point in time. Must be timezone-aware.

        Returns:
            {"rolled_back": N, "reactivated": N}
        """
        from datetime import timezone
        from sqlalchemy import text as sql_text

        rolled_back = 0
        reactivated = 0

        async with self._db.session() as session:
            # Find memories created after to_time
            rows = (await session.execute(
                sql_text("""
                    SELECT id FROM embeddings
                    WHERE user_id = :uid AND valid_from > :to_time
                      AND valid_until IS NULL
                """),
                {"uid": user_id, "to_time": to_time},
            )).fetchall()

            new_ids = [row.id for row in rows]
            if not new_ids:
                return {"rolled_back": 0, "reactivated": 0}

            # Invalidate these memories
            placeholders = ", ".join(f":id_{i}" for i in range(len(new_ids)))
            id_params = {f"id_{i}": nid for i, nid in enumerate(new_ids)}
            now = datetime.now(timezone.utc)

            result = await session.execute(
                sql_text(f"""
                    UPDATE embeddings SET valid_until = :now
                    WHERE id IN ({placeholders}) AND user_id = :uid
                """),
                {"now": now, "uid": user_id, **id_params},
            )
            rolled_back = result.rowcount

            # Reactivate predecessors (memories that were superseded by rolled-back ones)
            result = await session.execute(
                sql_text(f"""
                    UPDATE embeddings SET valid_until = NULL, superseded_by = NULL
                    WHERE user_id = :uid
                      AND superseded_by IN ({placeholders})
                """),
                {"uid": user_id, **id_params},
            )
            reactivated = result.rowcount

            # Also rollback graph edges created after to_time
            await session.execute(
                sql_text("""
                    UPDATE graph_edges
                    SET properties = jsonb_set(
                        COALESCE(properties, '{}'::jsonb),
                        '{valid_until}',
                        to_jsonb(CAST(:now AS text))
                    )
                    WHERE user_id = :uid
                      AND CAST(properties->>'valid_from' AS timestamptz) > :to_time
                      AND (properties->>'valid_until') IS NULL
                """),
                {"uid": user_id, "to_time": to_time, "now": now.isoformat()},
            )

            await session.commit()

        logger.info(
            "rollback_memories[%s] to=%s: rolled_back=%d reactivated=%d",
            user_id, to_time, rolled_back, reactivated,
        )
        return {"rolled_back": rolled_back, "reactivated": reactivated}

    # -- Data lifecycle APIs --

    async def delete_user_data(self, user_id: str) -> dict:
        """Delete ALL data for a user in a single transaction.

        Removes data from all tables (embeddings, conversations, graph, KV,
        emotion profiles, documents) atomically.

        Returns:
            {"deleted": {"embeddings": N, "conversations": N, ...}}
        """
        from sqlalchemy import text as sql_text

        tables = [
            ("embeddings", "user_id"),
            ("graph_edges", "user_id"),
            ("graph_nodes", "user_id"),
            ("conversations", "user_id"),
            ("conversation_sessions", "user_id"),
            ("key_values", "scope_id"),
            ("emotion_profiles", "user_id"),
            ("documents", "user_id"),
        ]

        deleted: dict[str, int] = {}
        async with self._db.session() as session:
            for table, id_col in tables:
                result = await session.execute(
                    sql_text(f"DELETE FROM {table} WHERE {id_col} = :uid"),
                    {"uid": user_id},
                )
                deleted[table] = result.rowcount
            await session.commit()

        logger.info("delete_user_data[%s]: %s", user_id, deleted)
        return {"deleted": deleted}

    async def export_user_data(self, user_id: str) -> dict:
        """Export ALL data for a user as a structured dict.

        Returns:
            {
                "memories": [...],
                "conversations": [...],
                "graph": {"nodes": [...], "edges": [...]},
                "kv": [...],
                "profile": {...} or None,
                "documents": [...],
            }
        """
        from sqlalchemy import text as sql_text

        result: dict = {}
        async with self._db.session() as session:
            # Memories
            rows = (await session.execute(
                sql_text(
                    "SELECT id, content, memory_type, metadata, created_at, "
                    "access_count, last_accessed_at, extracted_timestamp "
                    "FROM embeddings WHERE user_id = :uid ORDER BY created_at"
                ),
                {"uid": user_id},
            )).fetchall()
            result["memories"] = [
                {
                    "id": str(r.id), "content": r.content,
                    "memory_type": r.memory_type, "metadata": r.metadata,
                    "created_at": str(r.created_at) if r.created_at else None,
                    "access_count": r.access_count,
                    "last_accessed_at": str(r.last_accessed_at) if r.last_accessed_at else None,
                    "extracted_timestamp": str(r.extracted_timestamp) if r.extracted_timestamp else None,
                }
                for r in rows
            ]

            # Conversations
            rows = (await session.execute(
                sql_text(
                    "SELECT id, role, content, session_id, created_at "
                    "FROM conversations WHERE user_id = :uid ORDER BY created_at"
                ),
                {"uid": user_id},
            )).fetchall()
            result["conversations"] = [
                {
                    "id": str(r.id), "role": r.role, "content": r.content,
                    "session_id": r.session_id,
                    "created_at": str(r.created_at) if r.created_at else None,
                }
                for r in rows
            ]

            # Graph nodes
            rows = (await session.execute(
                sql_text(
                    "SELECT node_type, node_id, properties "
                    "FROM graph_nodes WHERE user_id = :uid"
                ),
                {"uid": user_id},
            )).fetchall()
            graph_nodes = [
                {"node_type": r.node_type, "node_id": r.node_id, "properties": r.properties}
                for r in rows
            ]

            # Graph edges
            rows = (await session.execute(
                sql_text(
                    "SELECT source_type, source_id, edge_type, target_type, target_id, properties "
                    "FROM graph_edges WHERE user_id = :uid"
                ),
                {"uid": user_id},
            )).fetchall()
            graph_edges = [
                {
                    "source_type": r.source_type, "source_id": r.source_id,
                    "edge_type": r.edge_type,
                    "target_type": r.target_type, "target_id": r.target_id,
                    "properties": r.properties,
                }
                for r in rows
            ]
            result["graph"] = {"nodes": graph_nodes, "edges": graph_edges}

            # KV
            rows = (await session.execute(
                sql_text(
                    "SELECT namespace, key, value, created_at, updated_at "
                    "FROM key_values WHERE scope_id = :uid"
                ),
                {"uid": user_id},
            )).fetchall()
            result["kv"] = [
                {
                    "namespace": r.namespace, "key": r.key, "value": r.value,
                    "created_at": str(r.created_at) if r.created_at else None,
                    "updated_at": str(r.updated_at) if r.updated_at else None,
                }
                for r in rows
            ]

            # Emotion profile
            row = (await session.execute(
                sql_text(
                    "SELECT * FROM emotion_profiles WHERE user_id = :uid"
                ),
                {"uid": user_id},
            )).first()
            if row:
                profile_dict = dict(row._mapping)
                # Convert non-serializable fields
                for k, v in profile_dict.items():
                    if hasattr(v, "isoformat"):
                        profile_dict[k] = v.isoformat()
                    elif hasattr(v, "hex"):
                        profile_dict[k] = str(v)
                result["profile"] = profile_dict
            else:
                result["profile"] = None

            # Documents
            rows = (await session.execute(
                sql_text(
                    "SELECT id, filename, file_type, category, object_key, created_at "
                    "FROM documents WHERE user_id = :uid ORDER BY created_at"
                ),
                {"uid": user_id},
            )).fetchall()
            result["documents"] = [
                {
                    "id": str(r.id), "filename": r.filename,
                    "file_type": r.file_type, "category": r.category,
                    "object_key": r.object_key,
                    "created_at": str(r.created_at) if r.created_at else None,
                }
                for r in rows
            ]

        return result

    # -- Analytics APIs --

    async def stats(self, user_id: str) -> dict:
        """Memory statistics for a user.

        Returns:
            {
                "total": N,
                "by_type": {"fact": N, "episodic": N, ...},
                "by_week": [{"week": "2025-W01", "count": N}, ...],
                "active_entities": N,
                "profile_summary": {...} or None,
            }
        """
        from sqlalchemy import text as sql_text

        async with self._db.session() as session:
            # Total memories
            total = (await session.execute(
                sql_text("SELECT COUNT(*) FROM embeddings WHERE user_id = :uid"),
                {"uid": user_id},
            )).scalar() or 0

            # By type
            rows = (await session.execute(
                sql_text(
                    "SELECT memory_type, COUNT(*) as cnt "
                    "FROM embeddings WHERE user_id = :uid "
                    "GROUP BY memory_type ORDER BY cnt DESC"
                ),
                {"uid": user_id},
            )).fetchall()
            by_type = {r.memory_type: r.cnt for r in rows}

            # By week (last 12 weeks)
            rows = (await session.execute(
                sql_text(
                    "SELECT to_char(created_at, 'IYYY-\"W\"IW') as week, COUNT(*) as cnt "
                    "FROM embeddings WHERE user_id = :uid "
                    "AND created_at > NOW() - INTERVAL '12 weeks' "
                    "GROUP BY week ORDER BY week"
                ),
                {"uid": user_id},
            )).fetchall()
            by_week = [{"week": r.week, "count": r.cnt} for r in rows]

            # Active entities (graph nodes)
            active_entities = (await session.execute(
                sql_text("SELECT COUNT(*) FROM graph_nodes WHERE user_id = :uid"),
                {"uid": user_id},
            )).scalar() or 0

            # Profile summary
            row = (await session.execute(
                sql_text(
                    "SELECT dominant_emotions, latest_state, last_reflected_at "
                    "FROM emotion_profiles WHERE user_id = :uid"
                ),
                {"uid": user_id},
            )).first()
            profile_summary = None
            if row:
                profile_summary = {
                    "dominant_emotions": row.dominant_emotions,
                    "latest_state": row.latest_state,
                    "last_reflected_at": str(row.last_reflected_at) if row.last_reflected_at else None,
                }

        return {
            "total": total,
            "by_type": by_type,
            "by_week": by_week,
            "active_entities": active_entities,
            "profile_summary": profile_summary,
        }

    async def cold_memories(
        self, user_id: str, threshold_days: int = 90, limit: int = 50,
    ) -> list[dict]:
        """Find memories that haven't been accessed in threshold_days.

        Args:
            user_id: User ID.
            threshold_days: Days since last access (or creation) to consider "cold".
            limit: Max results.

        Returns:
            List of memory dicts sorted by last_accessed_at ASC (coldest first).
        """
        from sqlalchemy import text as sql_text

        async with self._db.session() as session:
            rows = (await session.execute(
                sql_text("""
                    SELECT id, content, memory_type, metadata, created_at,
                           access_count, last_accessed_at
                    FROM embeddings
                    WHERE user_id = :uid
                      AND (
                        (last_accessed_at IS NOT NULL AND last_accessed_at < NOW() - INTERVAL '1 day' * :days)
                        OR (last_accessed_at IS NULL AND created_at < NOW() - INTERVAL '1 day' * :days)
                      )
                    ORDER BY COALESCE(last_accessed_at, created_at) ASC
                    LIMIT :lim
                """),
                {"uid": user_id, "days": threshold_days, "lim": limit},
            )).fetchall()

        return [
            {
                "id": str(r.id), "content": r.content,
                "memory_type": r.memory_type, "metadata": r.metadata,
                "created_at": str(r.created_at) if r.created_at else None,
                "access_count": r.access_count,
                "last_accessed_at": str(r.last_accessed_at) if r.last_accessed_at else None,
            }
            for r in rows
        ]

    async def entity_profile(self, user_id: str, entity: str) -> dict:
        """Get all information about an entity across all memory types.

        Searches embeddings (content mentions), graph edges, and conversations
        to build a comprehensive entity profile.

        Args:
            user_id: User ID.
            entity: Entity name to search for.

        Returns:
            {
                "entity": str,
                "facts": [...],
                "graph_relations": [...],
                "conversations": [...],
                "timeline": [...],
            }
        """
        from sqlalchemy import text as sql_text

        entity_lower = entity.lower()

        async with self._db.session() as session:
            # Facts: memories mentioning this entity
            rows = (await session.execute(
                sql_text("""
                    SELECT id, content, memory_type, metadata, created_at
                    FROM embeddings
                    WHERE user_id = :uid AND LOWER(content) LIKE :pattern
                    ORDER BY created_at DESC LIMIT 20
                """),
                {"uid": user_id, "pattern": f"%{entity_lower}%"},
            )).fetchall()
            facts = [
                {
                    "id": str(r.id), "content": r.content,
                    "memory_type": r.memory_type,
                    "created_at": str(r.created_at) if r.created_at else None,
                }
                for r in rows
            ]

            # Graph relations
            from neuromemory.services.graph_memory import GraphMemoryService
            graph_svc = GraphMemoryService(session)
            graph_relations = await graph_svc.find_entity_facts(user_id, entity, limit=20)

            # Conversations mentioning this entity
            rows = (await session.execute(
                sql_text("""
                    SELECT id, role, content, session_id, created_at
                    FROM conversations
                    WHERE user_id = :uid AND LOWER(content) LIKE :pattern
                    ORDER BY created_at DESC LIMIT 20
                """),
                {"uid": user_id, "pattern": f"%{entity_lower}%"},
            )).fetchall()
            conversations = [
                {
                    "id": str(r.id), "role": r.role, "content": r.content,
                    "session_id": r.session_id,
                    "created_at": str(r.created_at) if r.created_at else None,
                }
                for r in rows
            ]

            # Timeline: merge facts + conversations by time
            timeline = sorted(
                [
                    {"type": "memory", "content": f["content"], "time": f["created_at"]}
                    for f in facts if f["created_at"]
                ] + [
                    {"type": "conversation", "content": c["content"], "time": c["created_at"]}
                    for c in conversations if c["created_at"]
                ],
                key=lambda x: x["time"],
            )

        return {
            "entity": entity,
            "facts": facts,
            "graph_relations": graph_relations,
            "conversations": conversations,
            "timeline": timeline,
        }
