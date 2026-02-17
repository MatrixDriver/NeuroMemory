"""NeuroMemory main class (facade pattern)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
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
    (preferences, facts, episodes) from conversation messages using LLM.

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
    reflection_interval: int = 0  # Trigger reflection every N extractions (0 = disabled)


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
        _auto_extract: bool = True,
        _embedding: EmbeddingProvider | None = None,
        _llm: LLMProvider | None = None,
        _graph_enabled: bool = False,
    ):
        self._db = db
        self._on_message_added = _on_message_added
        self._on_session_closed = _on_session_closed
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

    async def _extract_single_message_async(self, user_id: str, session_id: str, messages: list):
        """异步后台提取单条消息的记忆，不阻塞主流程。

        所有异常都会被捕获并记录，不会影响对话响应。
        """
        try:
            await self._extract_single_message(user_id, session_id, messages)
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
            f"{result['preferences_extracted']} preferences, "
            f"{result['episodes_extracted']} episodes from batch for {user_id}"
        )

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

    async def query(self, cypher: str, params: dict | None = None):
        """Execute raw Cypher query. WARNING: bypasses user isolation."""
        from neuromemory.services.graph import GraphService
        async with self._db.session() as session:
            svc = GraphService(session)
            return await svc.query(cypher, params)


class NeuroMemory:
    """Main NeuroMemory facade - entry point for all operations.

    Args:
        database_url: PostgreSQL connection string
        embedding: Embedding provider (SiliconFlow/OpenAI/SentenceTransformer)
        llm: Optional LLM provider (for memory extraction)
        storage: Optional object storage (for files)
        extraction: Optional extraction strategy (for interval-based extraction)
        auto_extract: If True, automatically extract memories on add_message (default: True, like mem0)
        graph_enabled: Enable graph memory storage
        pool_size: Database connection pool size
        echo: Enable SQLAlchemy SQL logging

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

        # Manual extraction mode
        async with NeuroMemory(..., auto_extract=False) as nm:
            await nm.conversations.add_message(...)
            # No extraction yet
            await nm.extract_memories(user_id="alice")  # Manual trigger

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
        llm: Optional[LLMProvider] = None,
        storage: Optional[ObjectStorage] = None,
        extraction: Optional[ExtractionStrategy] = None,
        auto_extract: bool = True,
        graph_enabled: bool = False,
        pool_size: int = 10,
        echo: bool = False,
    ):
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

        # Extraction state tracking
        self._msg_counts: dict[tuple[str, str], int] = {}
        self._idle_tasks: dict[tuple[str, str], asyncio.Task] = {}
        self._active_sessions: set[tuple[str, str]] = set()
        self._extraction_counts: dict[str, int] = {}  # user_id -> count

        # Embedding cache for query deduplication (reduces API calls)
        self._embedding_cache: dict[str, list[float]] = {}
        self._embedding_cache_max_size = 100  # LRU-style limit

        # Set up callbacks if extraction is configured and LLM is available
        _has_extraction = bool(extraction and llm)
        on_msg = self._on_message_added if _has_extraction else None
        on_close = self._on_session_closed if _has_extraction else None

        # Sub-module facades
        self.kv = KVFacade(self._db)
        self.conversations = ConversationsFacade(
            self._db,
            _on_message_added=on_msg,
            _on_session_closed=on_close,
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
            logger.debug(f"Embedding cache hit for text length {len(text)}")
            return self._embedding_cache[text]

        # Compute embedding
        embedding = await self._embedding.embed(text)

        # Add to cache with LRU eviction
        if len(self._embedding_cache) >= self._embedding_cache_max_size:
            # Simple FIFO eviction (can upgrade to true LRU if needed)
            first_key = next(iter(self._embedding_cache))
            del self._embedding_cache[first_key]
            logger.debug(f"Evicted oldest embedding from cache")

        self._embedding_cache[text] = embedding
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

    async def _do_extraction(self, user_id: str, session_id: str) -> None:
        """Extract memories from unprocessed messages in a session."""
        try:
            messages = await self.conversations.get_unextracted_messages(
                user_id, session_id,
            )
            if not messages:
                return
            stats = await self.extract_memories(user_id, messages)
            logger.info(
                "Auto-extracted memories: user=%s session=%s "
                "prefs=%d facts=%d episodes=%d msgs=%d",
                user_id, session_id,
                stats["preferences_extracted"],
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

    async def add_memory(
        self,
        user_id: str,
        content: str,
        memory_type: str = "general",
        metadata: dict | None = None,
    ):
        """Add a memory with auto-generated embedding."""
        from neuromemory.services.search import SearchService
        async with self._db.session() as session:
            svc = SearchService(session, self._embedding, self._db.pg_search_available)
            return await svc.add_memory(user_id, content, memory_type, metadata)

    async def search(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        memory_type: str | None = None,
        created_after=None,
        created_before=None,
    ) -> list[dict]:
        """Semantic search for memories.

        **Performance**: Uses cached embedding to avoid redundant API calls.
        """
        from neuromemory.services.search import SearchService

        # 🚀 Use cached embedding
        query_embedding = await self._cached_embed(query)

        async with self._db.session() as session:
            svc = SearchService(session, self._embedding, self._db.pg_search_available)
            return await svc.search(
                user_id, query, limit, memory_type, created_after, created_before,
                query_embedding=query_embedding
            )

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

    async def extract_memories(self, user_id: str, messages):
        """Extract memories from conversation messages using LLM."""
        if not self._llm:
            raise RuntimeError("LLM provider required for memory extraction")
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
    ) -> dict:
        """Hybrid recall: memories + conversations + graph, merged and deduplicated.

        **v0.2.0 P1 Update**: Now searches both:
        1. Extracted memories (three-factor: relevance × recency × importance)
        2. Original conversation fragments (preserves dates, details)
        3. Graph entity traversal

        **Performance**: Uses cached embedding to avoid redundant API calls.

        Returns:
            {
                "vector_results": [...],       # extracted memories
                "conversation_results": [...], # original conversations (P1)
                "graph_results": [...],        # graph entities
                "merged": [...],               # deduplicated merge
            }
        """
        from neuromemory.services.search import SearchService, DEFAULT_DECAY_RATE

        # 🚀 Compute query embedding once, reuse for all searches
        query_embedding = await self._cached_embed(query)

        # 1. Search extracted memories (existing)
        vector_results = []
        async with self._db.session() as session:
            svc = SearchService(session, self._embedding, self._db.pg_search_available)
            vector_results = await svc.scored_search(
                user_id, query, limit,
                decay_rate=decay_rate or DEFAULT_DECAY_RATE,
                query_embedding=query_embedding,  # 传递预计算的 embedding
            )

        # 2. Search original conversations (P1: mem0-style)
        conversation_results = await self._search_conversations(
            user_id, query, limit,
            query_embedding=query_embedding,  # 传递预计算的 embedding
        )

        # 3. Search graph entities
        graph_results: list[dict] = []
        if self._graph_enabled:
            from neuromemory.services.graph_memory import GraphMemoryService
            async with self._db.session() as session:
                graph_svc = GraphMemoryService(session)
                graph_results = await graph_svc.find_entity_facts(
                    user_id, query, limit,
                )
                user_facts = await graph_svc.find_entity_facts(
                    user_id, user_id, limit,
                )
                graph_results.extend(user_facts)

        # 4. Fetch emotion profile for user context
        emotion_context: str | None = None
        try:
            from sqlalchemy import text as sql_text
            async with self._db.session() as session:
                row = (await session.execute(
                    sql_text("""
                        SELECT latest_state, dominant_emotions
                        FROM emotion_profiles WHERE user_id = :uid
                    """),
                    {"uid": user_id},
                )).first()
                if row and row.latest_state:
                    emotion_context = row.latest_state
        except Exception as e:
            logger.debug("Failed to fetch emotion profile: %s", e)

        # Deduplicate by content
        seen_contents: set[str] = set()
        merged: list[dict] = []

        # Inject emotion profile as leading context (helps open-domain questions)
        if emotion_context:
            merged.append({
                "content": f"[Emotion Profile] {emotion_context}",
                "source": "emotion_profile",
                "memory_type": "emotion_profile",
            })

        for r in vector_results:
            content = r.get("content", "")
            if content not in seen_contents:
                seen_contents.add(content)
                entry = {**r, "source": "vector"}
                # Enrich content with metadata for LLM context
                prefix_parts: list[str] = []
                ts = r.get("extracted_timestamp")
                if ts:
                    ts_str = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
                    prefix_parts.append(ts_str)
                meta = r.get("metadata") or {}
                emotion = meta.get("emotion") if isinstance(meta, dict) else None
                if emotion and isinstance(emotion, dict):
                    label = emotion.get("label", "")
                    valence = emotion.get("valence")
                    if label:
                        prefix_parts.append(f"sentiment: {label}")
                    elif valence is not None:
                        tone = "positive" if valence > 0.2 else "negative" if valence < -0.2 else "neutral"
                        prefix_parts.append(f"sentiment: {tone}")
                if prefix_parts:
                    entry["content"] = f"[{' | '.join(prefix_parts)}] {content}"
                merged.append(entry)

        for r in conversation_results:
            content = r.get("content", "")
            if content not in seen_contents:
                seen_contents.add(content)
                merged.append({**r, "source": "conversation"})

        for r in graph_results:
            content = r.get("content", "")
            if content and content not in seen_contents:
                seen_contents.add(content)
                merged.append({**r, "source": "graph"})

        return {
            "vector_results": vector_results,
            "conversation_results": conversation_results,
            "graph_results": graph_results,
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
            asyncio.create_task(_safe_reflect())
            return None
        return await self._reflect_impl(user_id, batch_size)

    async def _reflect_impl(
        self,
        user_id: str,
        batch_size: int = 50,
    ) -> dict:
        """Internal implementation of reflect()."""
        if not self._llm:
            raise RuntimeError("LLM provider required for reflection")

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
