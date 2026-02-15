"""Memory extraction service - Extract and store memories from conversations."""

from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from neuromemory.models.conversation import Conversation
from neuromemory.models.memory import Embedding
from neuromemory.providers.embedding import EmbeddingProvider
from neuromemory.providers.llm import LLMProvider
from neuromemory.services.kv import KVService

logger = logging.getLogger(__name__)


class MemoryExtractionService:
    """Service for extracting memories from conversations using LLM."""

    def __init__(
        self,
        db: AsyncSession,
        embedding: EmbeddingProvider,
        llm: LLMProvider,
        graph_enabled: bool = False,
    ):
        self.db = db
        self._embedding = embedding
        self._llm = llm
        self._graph_enabled = graph_enabled

    async def extract_from_messages(
        self,
        user_id: str,
        messages: list[Conversation],
    ) -> dict[str, int]:
        """Extract memories from a list of conversation messages.

        Returns:
            Statistics: {preferences_extracted, facts_extracted, episodes_extracted,
                        triples_extracted, messages_processed}
        """
        if not messages:
            return {
                "preferences_extracted": 0,
                "facts_extracted": 0,
                "episodes_extracted": 0,
                "triples_extracted": 0,
                "messages_processed": 0,
            }

        message_dicts = [
            {
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }
            for msg in messages
        ]

        classified = await self._classify_messages(message_dicts, user_id)
        logger.info(f"分类完成: {len(classified.get('preferences', []))} prefs, "
                   f"{len(classified.get('facts', []))} facts, "
                   f"{len(classified.get('episodes', []))} episodes, "
                   f"{len(classified.get('triples', []))} triples")

        try:
            prefs_count = await self._store_preferences(user_id, classified["preferences"])
            logger.info(f"✅ 存储 preferences 成功: {prefs_count}")
        except Exception as e:
            logger.error(f"❌ 存储 preferences 失败: {e}", exc_info=True)
            prefs_count = 0

        try:
            facts_count = await self._store_facts(user_id, classified["facts"])
            logger.info(f"✅ 存储 facts 成功: {facts_count}")
        except Exception as e:
            logger.error(f"❌ 存储 facts 失败: {e}", exc_info=True)
            facts_count = 0

        try:
            episodes_count = await self._store_episodes(user_id, classified["episodes"])
            logger.info(f"✅ 存储 episodes 成功: {episodes_count}")
        except Exception as e:
            logger.error(f"❌ 存储 episodes 失败: {e}", exc_info=True)
            episodes_count = 0

        triples_count = 0
        if self._graph_enabled:
            try:
                logger.info(f"开始存储 triples: {len(classified.get('triples', []))} 个")
                triples_count = await self._store_triples(user_id, classified["triples"])
                logger.info(f"✅ 存储 triples 成功: {triples_count}")
            except Exception as e:
                logger.error(f"❌ 存储 triples 失败: {e}", exc_info=True)
                triples_count = 0

        # 统一提交所有记忆（preferences, facts, episodes, triples）
        # 保证原子性：要么全部成功，要么全部失败
        total_count = prefs_count + facts_count + episodes_count + triples_count
        if total_count > 0:
            try:
                await self.db.commit()
                logger.info(f"✅ 所有记忆已提交 (prefs={prefs_count}, facts={facts_count}, "
                           f"episodes={episodes_count}, triples={triples_count})")
            except Exception as e:
                logger.error(f"❌ 提交记忆失败，回滚所有更改: {e}", exc_info=True)
                try:
                    await self.db.rollback()
                except Exception:
                    pass
                # 提交失败，所有计数归零
                prefs_count = facts_count = episodes_count = triples_count = 0

        return {
            "preferences_extracted": prefs_count,
            "facts_extracted": facts_count,
            "episodes_extracted": episodes_count,
            "triples_extracted": triples_count,
            "messages_processed": len(messages),
        }

    async def _classify_messages(
        self,
        messages: list[dict],
        user_id: str,
    ) -> dict[str, list[dict]]:
        """Classify messages using LLM."""
        conversation_text = self._format_conversation(messages)

        # Determine extraction language (KV preference > auto-detect > default)
        language = await self._get_extraction_language(user_id, conversation_text)

        prompt = self._build_classification_prompt(conversation_text, language)

        try:
            result_text = await self._llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2048,
            )
            extracted = self._parse_classification_result(result_text)
            return extracted
        except Exception as e:
            logger.error("Classification failed: %s", e, exc_info=True)
            return {"preferences": [], "facts": [], "episodes": [], "triples": []}

    def _format_conversation(self, messages: list[dict]) -> str:
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "")
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    async def _get_extraction_language(
        self,
        user_id: str,
        conversation_text: str,
    ) -> str:
        """
        Determine extraction prompt language.

        Priority:
        1. KV user preference (persistent setting)
        2. Auto-detect current conversation language
        3. Default "en"
        """
        # Check KV preference
        kv_service = KVService(self.db)
        lang_kv = await kv_service.get("preferences", user_id, "language")

        if lang_kv and lang_kv.value in ["en", "zh"]:
            # If preference exists, check if language switched
            detected = self._detect_language(conversation_text)
            if detected != lang_kv.value:
                # Language switch: update preference if high confidence
                confidence = self._detect_language_confidence(conversation_text)
                if confidence > 0.8:
                    logger.info(
                        f"Language preference updated: {user_id} {lang_kv.value} → {detected}"
                    )
                    await kv_service.set("preferences", user_id, "language", detected)
                    return detected
            return lang_kv.value

        # First time: auto-detect and save
        detected = self._detect_language(conversation_text)
        await kv_service.set("preferences", user_id, "language", detected)
        return detected

    def _detect_language(self, text: str) -> str:
        """Simple language detection based on Chinese character ratio."""
        if not text:
            return "en"

        chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        ratio = chinese_chars / len(text)
        return "zh" if ratio > 0.3 else "en"

    def _detect_language_confidence(self, text: str) -> float:
        """
        Language detection confidence (0-1).

        Returns high confidence if one language dominates (>80%).
        """
        if not text:
            return 0.5

        chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        english_chars = sum(1 for c in text if c.isalpha() and c.isascii())
        total = chinese_chars + english_chars

        if total == 0:
            return 0.5

        zh_ratio = chinese_chars / total
        en_ratio = english_chars / total
        return max(zh_ratio, en_ratio)

    def _build_classification_prompt(self, conversation: str, language: str) -> str:
        """Build classification prompt in the specified language."""
        if language == "zh":
            return self._build_zh_prompt(conversation)
        else:
            return self._build_en_prompt(conversation)

    def _build_zh_prompt(self, conversation: str) -> str:
        """Build Chinese classification prompt (original)."""
        triples_section = ""
        triples_output = ""
        if self._graph_enabled:
            triples_section = """
5. **Triples（实体关系三元组）**: 从 Facts 和 Episodes 中提取的结构化关系
   - 格式: {{"subject": "主体", "subject_type": "类型", "relation": "关系", "object": "客体", "object_type": "类型", "content": "原始描述", "confidence": 0.0-1.0}}
   - subject_type/object_type 可选: user, person, organization, location, event, skill, concept, entity
   - Facts 关系: works_at, lives_in, has_skill, studied_at, uses, knows
   - Episodes 关系: met (见面), attended (参加), visited (访问), occurred_at (发生地点), occurred_on (发生时间)
   - 用户自身 subject 填 "user"，subject_type 填 "user"
   - 每个 Fact 和 Episode 尽量提取对应的 triple"""
            triples_output = ',\n  "triples": [...]'

        return f"""分析以下对话，提取用户的记忆信息。请严格按照 JSON 格式返回结果。

对话内容：
```
{conversation}
```

请提取以下记忆：

1. **Preferences（偏好）**: 用户的喜好、习惯、设置
   - 格式: {{"key": "偏好名称", "value": "偏好值", "confidence": 0.0-1.0}}
   - key 应该用英文，value 可以是中文

2. **Facts（事实）**: 用户的客观信息
   - 格式: {{"content": "事实描述", "category": "分类", "confidence": 0.0-1.0, "importance": 1-10, "emotion": {{"valence": -1.0~1.0, "arousal": 0.0~1.0, "label": "情感描述"}} 或 null}}
   - category 可选: work, skill, hobby, personal, education, location
   - importance: 对用户的重要程度（1=随口一提, 5=日常信息, 9=非常重要如生日/重大事件, 10=核心身份信息）
   - emotion: 如果对话中有明显情感色彩则填写，否则设为 null。valence: 正面(1.0)/负面(-1.0)，arousal: 高兴奋(1.0)/低兴奋(0.0)

3. **Episodes（情景）**: 事件、经历、时间相关信息
   - 格式: {{"content": "事件描述", "timestamp": "时间信息或null", "people": ["人名1", "人名2"], "location": "地点或null", "confidence": 0.0-1.0, "importance": 1-10, "emotion": {{"valence": -1.0~1.0, "arousal": 0.0~1.0, "label": "情感描述"}} 或 null}}
   - people: 事件中涉及的人物列表（不包括用户自己）
   - location: 事件发生的地点
   - importance 和 emotion 同 Facts 定义

4. **注意事项**:
   - importance: 根据内容对用户生活的重要程度打分
   - emotion: 只标注对话文本中明显表达的情感，不推测用户内心感受
{triples_section}

要求：
- 只提取明确提到的信息，不要推测
- confidence 表示提取的确信度 (0.0-1.0)
- 如果某类没有信息，返回空列表
- 必须返回有效的 JSON 格式，不要有其他文字说明

返回格式（只返回 JSON，不要其他内容）：
```json
{{
  "preferences": [...],
  "facts": [...],
  "episodes": [...]{triples_output}
}}
```"""

    def _build_en_prompt(self, conversation: str) -> str:
        """Build English classification prompt for English conversations."""
        triples_section = ""
        triples_output = ""
        if self._graph_enabled:
            triples_section = """
5. **Triples (Entity-Relation Triples)**: Structured relationships extracted from Facts and Episodes
   - Format: {{"subject": "entity", "subject_type": "type", "relation": "relation", "object": "entity", "object_type": "type", "content": "original description", "confidence": 0.0-1.0}}
   - subject_type/object_type options: user, person, organization, location, event, skill, concept, entity
   - Facts relations: works_at, lives_in, has_skill, studied_at, uses, knows
   - Episodes relations: met (met someone), attended (attended event), visited (visited place), occurred_at (location), occurred_on (time)
   - For user's own: subject="user", subject_type="user"
   - Extract corresponding triple for each Fact and Episode when possible"""
            triples_output = ',\n  "triples": [...]'

        return f"""Extract structured memory information from the following conversation. Return results strictly in JSON format.

Conversation:
```
{conversation}
```

Extract the following memories:

1. **Preferences**: User's likes, dislikes, habits, settings
   - Format: {{"key": "preference_name", "value": "preference_value", "confidence": 0.0-1.0}}
   - Key should be in English, value can be in any language

2. **Facts**: Objective information about the user
   - Format: {{"content": "fact description", "category": "category", "confidence": 0.0-1.0, "importance": 1-10, "emotion": {{"valence": -1.0~1.0, "arousal": 0.0~1.0, "label": "emotion"}} or null}}
   - Category options: work, skill, hobby, personal, education, location
   - Importance: significance to user's life (1=casual mention, 5=daily info, 9=very important like birthday/major events, 10=core identity)
   - Emotion: only tag if conversation explicitly shows emotion, otherwise null. valence: positive(1.0)/negative(-1.0), arousal: high(1.0)/low(0.0)

3. **Episodes**: Events, experiences, temporal information
   - Format: {{"content": "event description", "timestamp": "time info or null", "people": ["person1", "person2"], "location": "place or null", "confidence": 0.0-1.0, "importance": 1-10, "emotion": {{"valence": -1.0~1.0, "arousal": 0.0~1.0, "label": "emotion"}} or null}}
   - people: List of people involved in the event (excluding the user)
   - location: Where the event occurred
   - Importance and emotion: same as Facts

4. **Guidelines**:
   - Importance: rate based on significance to user's life
   - Emotion: only tag emotions explicitly expressed in conversation, do not infer
{triples_section}

Requirements:
- Only extract explicitly mentioned information, do not infer
- Confidence represents extraction certainty (0.0-1.0)
- Return empty list if no information for a category
- Must return valid JSON format only, no additional text

Return format (JSON only, no other content):
```json
{{
  "preferences": [...],
  "facts": [...],
  "episodes": [...]{triples_output}
}}
```"""

    def _parse_classification_result(self, result_text: str) -> dict[str, list[dict]]:
        """Parse LLM classification result."""
        try:
            text = result_text.strip()

            if "```json" in text:
                start = text.find("```json") + 7
                end = text.find("```", start)
                text = text[start:end].strip()
            elif "```" in text:
                start = text.find("```") + 3
                end = text.find("```", start)
                text = text[start:end].strip()

            result = json.loads(text)

            if not isinstance(result, dict):
                raise ValueError("Result is not a dictionary")

            preferences = result.get("preferences", [])
            facts = result.get("facts", [])
            episodes = result.get("episodes", [])
            triples = result.get("triples", [])

            if not isinstance(preferences, list):
                preferences = []
            if not isinstance(facts, list):
                facts = []
            if not isinstance(episodes, list):
                episodes = []
            if not isinstance(triples, list):
                triples = []

            return {
                "preferences": preferences,
                "facts": facts,
                "episodes": episodes,
                "triples": triples,
            }

        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON from classification result: %s", e)
            return {"preferences": [], "facts": [], "episodes": [], "triples": []}
        except Exception as e:
            logger.error("Error parsing classification result: %s", e)
            return {"preferences": [], "facts": [], "episodes": [], "triples": []}

    async def _store_preferences(
        self,
        user_id: str,
        preferences: list[dict],
    ) -> int:
        count = 0
        kv_service = KVService(self.db)
        for pref in preferences:
            key = pref.get("key")
            value = pref.get("value")
            if not key or not value:
                continue
            try:
                await kv_service.set(
                    namespace="preferences",
                    scope_id=user_id,
                    key=key,
                    value=value,
                )
                count += 1
            except Exception as e:
                logger.error("Failed to store preference %s: %s", key, e, exc_info=True)
                # 不在这里 rollback，让异常向上传播或继续处理下一个
                # 最终的 commit/rollback 由 extract_from_messages 统一处理
        return count

    async def _store_facts(
        self,
        user_id: str,
        facts: list[dict],
    ) -> int:
        count = 0
        for fact in facts:
            content = fact.get("content")
            category = fact.get("category", "general")
            confidence = fact.get("confidence", 1.0)
            importance = fact.get("importance")
            emotion = fact.get("emotion")
            if not content:
                continue
            try:
                embedding_vector = await self._embedding.embed(content)
                meta = {
                    "category": category,
                    "confidence": confidence,
                    "extracted_from": "conversation",
                }
                if importance is not None:
                    meta["importance"] = importance
                if emotion and isinstance(emotion, dict):
                    meta["emotion"] = {
                        "valence": emotion.get("valence", 0),
                        "arousal": emotion.get("arousal", 0),
                        "label": emotion.get("label", ""),
                    }
                embedding_obj = Embedding(
                    user_id=user_id,
                    content=content,
                    embedding=embedding_vector,
                    memory_type="fact",
                    metadata_=meta,
                )
                self.db.add(embedding_obj)
                count += 1
            except Exception as e:
                logger.error("Failed to store fact: %s", e, exc_info=True)
                # 不在这里 rollback，让异常向上传播或继续处理下一个
                # 最终的 commit/rollback 由 extract_from_messages 统一处理

        # 不在这里 commit，等待所有类型的记忆都存储完后统一 commit（保证原子性）
        return count

    async def _store_episodes(
        self,
        user_id: str,
        episodes: list[dict],
    ) -> int:
        count = 0
        for episode in episodes:
            content = episode.get("content")
            timestamp = episode.get("timestamp")
            people = episode.get("people")  # v0.2.0: Extract people
            location = episode.get("location")  # v0.2.0: Extract location
            confidence = episode.get("confidence", 1.0)
            importance = episode.get("importance")
            emotion = episode.get("emotion")
            if not content:
                continue
            try:
                embedding_vector = await self._embedding.embed(content)
                meta = {
                    "timestamp": timestamp,
                    "confidence": confidence,
                    "extracted_from": "conversation",
                }
                # v0.2.0: Store people and location in metadata
                if people and isinstance(people, list):
                    meta["people"] = people
                if location:
                    meta["location"] = location
                if importance is not None:
                    meta["importance"] = importance
                if emotion and isinstance(emotion, dict):
                    meta["emotion"] = {
                        "valence": emotion.get("valence", 0),
                        "arousal": emotion.get("arousal", 0),
                        "label": emotion.get("label", ""),
                    }
                logger.debug(f"准备存储 episode: {content[:50]}...")
                embedding_obj = Embedding(
                    user_id=user_id,
                    content=content,
                    embedding=embedding_vector,
                    memory_type="episodic",
                    metadata_=meta,
                )
                logger.debug(f"调用 db.add()...")
                self.db.add(embedding_obj)
                logger.debug(f"db.add() 成功")
                count += 1
            except Exception as e:
                logger.error("Failed to store episode: %s", e, exc_info=True)
                # 不在这里 rollback，让异常向上传播或继续处理下一个
                # 最终的 commit/rollback 由 extract_from_messages 统一处理

        # 不在这里 commit，等待所有类型的记忆都存储完后统一 commit（保证原子性）
        return count

    async def _store_triples(
        self,
        user_id: str,
        triples: list[dict],
    ) -> int:
        """Store entity-relation triples into the graph."""
        if not triples:
            return 0
        try:
            from neuromemory.services.graph_memory import GraphMemoryService
            graph_svc = GraphMemoryService(self.db)
            return await graph_svc.store_triples(user_id, triples)
        except Exception as e:
            logger.error("Failed to store triples: %s", e)
            return 0
