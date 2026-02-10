"""Memory extraction service - Extract and store memories from conversations"""

import logging
from typing import Dict, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from server.app.models.conversation import Conversation
from server.app.services.classifier import get_classifier
from server.app.services.embedding import get_embedding_service
from server.app.services import preferences as pref_service

logger = logging.getLogger(__name__)


class MemoryExtractionService:
    """Service for extracting memories from conversations using LLM"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.classifier = get_classifier()
        self.embedding_service = get_embedding_service()

    async def extract_from_messages(
        self,
        tenant_id: UUID,
        user_id: str,
        messages: List[Conversation],
    ) -> Dict[str, int]:
        """Extract memories from a list of conversation messages

        Args:
            tenant_id: Tenant UUID
            user_id: User identifier
            messages: List of Conversation objects

        Returns:
            Statistics about extracted memories:
            {
                "preferences_extracted": 2,
                "facts_extracted": 5,
                "episodes_extracted": 3,
                "messages_processed": 10
            }
        """
        if not messages:
            logger.info("No messages to process")
            return {
                "preferences_extracted": 0,
                "facts_extracted": 0,
                "episodes_extracted": 0,
                "messages_processed": 0,
            }

        # Convert Conversation objects to simple dicts for classifier
        message_dicts = [
            {
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }
            for msg in messages
        ]

        # Classify messages using LLM
        logger.info(f"Classifying {len(message_dicts)} messages for user {user_id}")
        classified = self.classifier.classify_messages(message_dicts, user_id)

        # Store extracted memories
        prefs_count = await self._store_preferences(
            tenant_id, user_id, classified["preferences"]
        )
        facts_count = await self._store_facts(
            tenant_id, user_id, classified["facts"]
        )
        episodes_count = await self._store_episodes(
            tenant_id, user_id, classified["episodes"]
        )

        logger.info(
            f"Extraction complete: {prefs_count} preferences, "
            f"{facts_count} facts, {episodes_count} episodes"
        )

        return {
            "preferences_extracted": prefs_count,
            "facts_extracted": facts_count,
            "episodes_extracted": episodes_count,
            "messages_processed": len(messages),
        }

    async def _store_preferences(
        self,
        tenant_id: UUID,
        user_id: str,
        preferences: List[Dict],
    ) -> int:
        """Store extracted preferences

        Args:
            tenant_id: Tenant UUID
            user_id: User identifier
            preferences: List of preference dicts with 'key', 'value', 'confidence'

        Returns:
            Number of preferences stored
        """
        count = 0
        for pref in preferences:
            key = pref.get("key")
            value = pref.get("value")
            confidence = pref.get("confidence", 1.0)

            if not key or not value:
                logger.warning(f"Invalid preference: {pref}")
                continue

            try:
                # Use upsert to avoid duplicates
                await pref_service.set_preference(
                    db=self.db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    key=key,
                    value=value,
                )
                count += 1
                logger.debug(
                    f"Stored preference: {key}={value} (confidence: {confidence})"
                )
            except Exception as e:
                logger.error(f"Failed to store preference {key}: {e}")

        return count

    async def _store_facts(
        self,
        tenant_id: UUID,
        user_id: str,
        facts: List[Dict],
    ) -> int:
        """Store extracted facts as embeddings

        Args:
            tenant_id: Tenant UUID
            user_id: User identifier
            facts: List of fact dicts with 'content', 'category', 'confidence'

        Returns:
            Number of facts stored
        """
        from server.app.models.memory import Embedding

        count = 0
        for fact in facts:
            content = fact.get("content")
            category = fact.get("category", "general")
            confidence = fact.get("confidence", 1.0)

            if not content:
                logger.warning(f"Invalid fact: {fact}")
                continue

            try:
                # Generate embedding
                embedding_vector = await self.embedding_service.embed(content)

                # Create Embedding record with memory_type = 'fact'
                embedding_obj = Embedding(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    content=content,
                    embedding=embedding_vector,
                    memory_type="fact",
                    metadata_={
                        "category": category,
                        "confidence": confidence,
                        "extracted_from": "conversation",
                    },
                )
                self.db.add(embedding_obj)
                count += 1
                logger.debug(
                    f"Stored fact: {content[:50]}... (category: {category}, "
                    f"confidence: {confidence})"
                )
            except Exception as e:
                logger.error(f"Failed to store fact: {e}")

        # Commit all facts at once
        if count > 0:
            await self.db.commit()

        return count

    async def _store_episodes(
        self,
        tenant_id: UUID,
        user_id: str,
        episodes: List[Dict],
    ) -> int:
        """Store extracted episodes as embeddings

        Args:
            tenant_id: Tenant UUID
            user_id: User identifier
            episodes: List of episode dicts with 'content', 'timestamp', 'confidence'

        Returns:
            Number of episodes stored
        """
        from server.app.models.memory import Embedding

        count = 0
        for episode in episodes:
            content = episode.get("content")
            timestamp = episode.get("timestamp")
            confidence = episode.get("confidence", 1.0)

            if not content:
                logger.warning(f"Invalid episode: {episode}")
                continue

            try:
                # Generate embedding
                embedding_vector = await self.embedding_service.embed(content)

                # Create Embedding record with memory_type = 'episodic'
                embedding_obj = Embedding(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    content=content,
                    embedding=embedding_vector,
                    memory_type="episodic",
                    metadata_={
                        "timestamp": timestamp,
                        "confidence": confidence,
                        "extracted_from": "conversation",
                    },
                )
                self.db.add(embedding_obj)
                count += 1
                logger.debug(
                    f"Stored episode: {content[:50]}... (timestamp: {timestamp}, "
                    f"confidence: {confidence})"
                )
            except Exception as e:
                logger.error(f"Failed to store episode: {e}")

        # Commit all episodes at once
        if count > 0:
            await self.db.commit()

        return count
