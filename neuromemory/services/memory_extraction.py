"""Memory extraction service - Extract and store memories from conversations."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from neuromemory.models.conversation import Conversation
from neuromemory.models.memory import Embedding
from neuromemory.providers.embedding import EmbeddingProvider
from neuromemory.providers.llm import LLMProvider
from neuromemory.services.kv import KVService
from neuromemory.services.temporal import TemporalExtractor

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
        self._temporal = TemporalExtractor()

    async def extract_from_messages(
        self,
        user_id: str,
        messages: list[Conversation],
    ) -> dict[str, int]:
        """Extract memories from a list of conversation messages.

        Returns:
            Statistics: {facts_extracted, episodes_extracted,
                        triples_extracted, messages_processed}
        """
        if not messages:
            return {
                "facts_extracted": 0,
                "episodes_extracted": 0,
                "triples_extracted": 0,
                "messages_processed": 0,
            }

        message_dicts = []
        for msg in messages:
            # Prefer metadata session_timestamp over created_at for accurate
            # temporal context (eval pipeline backfills this with dataset time)
            meta = getattr(msg, "metadata_", None) or {}
            ts = meta.get("session_timestamp") or (
                msg.created_at.isoformat() if msg.created_at else None
            )
            message_dicts.append({
                "role": msg.role,
                "content": msg.content,
                "created_at": ts,
            })

        classified = await self._classify_messages(message_dicts, user_id)
        logger.info(f"分类完成: {len(classified.get('facts', []))} facts, "
                   f"{len(classified.get('episodes', []))} episodes, "
                   f"{len(classified.get('triples', []))} triples")

        # Parse session_timestamp for temporal post-processing
        session_ts = self._get_session_timestamp(message_dicts)
        ref_time: datetime | None = None
        if session_ts:
            try:
                ref_time = datetime.fromisoformat(session_ts)
                if ref_time.tzinfo is None:
                    ref_time = ref_time.replace(tzinfo=timezone.utc)
            except ValueError:
                ref_time = None

        # Pre-filter valid items
        valid_facts = [f for f in classified.get("facts", []) if f.get("content")]
        valid_episodes = [e for e in classified.get("episodes", []) if e.get("content")]

        # Embed facts and episodes in parallel (2 API calls → 1 round-trip)
        async def _embed_or_empty(contents: list[str]) -> list:
            if not contents:
                return []
            return await self._embedding.embed_batch(contents)

        fact_vectors: list[Any] = []
        episode_vectors: list[Any] = []
        if valid_facts or valid_episodes:
            _results = await asyncio.gather(
                _embed_or_empty([f["content"] for f in valid_facts]),
                _embed_or_empty([e["content"] for e in valid_episodes]),
                return_exceptions=True,
            )
            if isinstance(_results[0], Exception):
                logger.error(f"❌ facts embedding 失败: {_results[0]}", exc_info=_results[0])
            else:
                fact_vectors = _results[0]
            if isinstance(_results[1], Exception):
                logger.error(f"❌ episodes embedding 失败: {_results[1]}", exc_info=_results[1])
            else:
                episode_vectors = _results[1]

        try:
            facts_count = await self._store_facts(user_id, valid_facts, ref_time, pre_vectors=fact_vectors)
            logger.info(f"✅ 存储 facts 成功: {facts_count}")
        except Exception as e:
            logger.error(f"❌ 存储 facts 失败: {e}", exc_info=True)
            facts_count = 0

        try:
            episodes_count = await self._store_episodes(user_id, valid_episodes, ref_time, pre_vectors=episode_vectors)
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

        # Store profile updates to KV store
        profile_updates = classified.get("profile_updates", {})
        if profile_updates:
            try:
                await self._store_profile_updates(user_id, profile_updates)
                logger.info(f"✅ 存储 profile_updates 成功: {list(profile_updates.keys())}")
            except Exception as e:
                logger.error(f"❌ 存储 profile_updates 失败: {e}", exc_info=True)

        # 统一提交所有记忆（facts, episodes, triples）
        # 保证原子性：要么全部成功，要么全部失败
        total_count = facts_count + episodes_count + triples_count
        if total_count > 0:
            try:
                await self.db.commit()
                logger.info(f"✅ 所有记忆已提交 (facts={facts_count}, "
                           f"episodes={episodes_count}, triples={triples_count})")
            except Exception as e:
                logger.error(f"❌ 提交记忆失败，回滚所有更改: {e}", exc_info=True)
                try:
                    await self.db.rollback()
                except Exception:
                    pass
                # 提交失败，所有计数归零
                facts_count = episodes_count = triples_count = 0

        return {
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
        session_timestamp = self._get_session_timestamp(messages)

        # Determine extraction language (KV preference > auto-detect > default)
        language = await self._get_extraction_language(user_id, conversation_text)

        prompt = self._build_classification_prompt(conversation_text, language, session_timestamp)

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
            return {"facts": [], "episodes": [], "triples": []}

    def _format_conversation(self, messages: list[dict]) -> str:
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "")
            ts = msg.get("created_at", "")
            if ts:
                lines.append(f"[{ts}] {role}: {content}")
            else:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _get_session_timestamp(self, messages: list[dict]) -> str | None:
        """Get the latest timestamp from messages as session reference time."""
        for msg in reversed(messages):
            ts = msg.get("created_at")
            if ts:
                return ts
        return None

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
        lang_kv = await kv_service.get("profile", user_id, "language")

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
                    await kv_service.set("profile", user_id, "language", detected)
                    return detected
            return lang_kv.value

        # First time: auto-detect and save
        detected = self._detect_language(conversation_text)
        await kv_service.set("profile", user_id, "language", detected)
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

    def _build_classification_prompt(self, conversation: str, language: str, session_timestamp: str | None = None) -> str:
        """Build classification prompt in the specified language."""
        if language == "zh":
            return self._build_zh_prompt(conversation, session_timestamp)
        else:
            return self._build_en_prompt(conversation, session_timestamp)

    def _build_zh_prompt(self, conversation: str, session_timestamp: str | None = None) -> str:
        """Build Chinese classification prompt (original)."""
        triples_section = ""
        triples_output = ""
        profile_num = 4
        if self._graph_enabled:
            profile_num = 5
            triples_section = """
4. **Triples（实体关系三元组）**: 从 Facts 和 Episodes 中提取的结构化关系
   - 格式: {{"subject": "主体", "subject_type": "类型", "relation": "关系", "object": "客体", "object_type": "类型", "content": "原始描述", "confidence": 0.0-1.0}}
   - subject_type/object_type 可选: user, person, organization, location, skill, entity（**禁止使用 concept**）
   - **object 必须是可命名的真实实体**：具体的人、地点、组织、工具、技能、语言、具体活动（如"徒步"、"国际象棋"）
   - **禁止**将抽象概念、描述性短语、情绪作为 object（如"贝多芬的音乐"、"压力"、"美好生活"）
   - Facts 关系（优先使用）: works_at, lives_in, has_skill, studied_at, uses, knows, hobby, owns, speaks, born_in
   - Episodes 关系: met (见面), attended (参加活动), visited (访问地点), occurred_at (发生地点)
   - 用户自身 subject 填 "user"，subject_type 填 "user"
   - confidence < 0.6 的 triple 不要输出
   - 只为有明确实体 object 的 Fact/Episode 提取 triple，没有则跳过"""
            triples_output = ',\n  "triples": [...]'

        temporal_section = ""
        if session_timestamp:
            temporal_section = f"""
**时间上下文**：
   - 当前对话会话时间: {session_timestamp}
   - 将所有相对时间表达转换为绝对日期（基于会话时间计算）
   - 示例："昨天" → 计算实际日期，"上周" → 计算日期范围，"三年前" → 计算年份
   - 将计算后的绝对时间存入 "timestamp" 字段，使用 ISO 8601 格式（如 "2023-05-06"）
   - 同时将原始时间表达保留在 "timestamp_original" 字段中
"""

        profile_section_zh = f"""{profile_num}. **Profile Updates（用户画像更新）**: 从对话中提取的用户画像信息
   - 只在对话中**明确提到**相关信息时才输出对应字段，没有信息的字段不要包含
   - identity: 用户的姓名、年龄、性别等核心身份信息（字符串，如"张三，男，28岁"）
   - occupation: 用户的职业/公司/职位信息（字符串，如"Google 软件工程师"）
   - interests: 用户的兴趣爱好列表（字符串数组，如["摄影", "徒步"]）
   - preferences: 用户的偏好和习惯（字符串数组，如["喜欢喝咖啡", "偏好深色模式"]）
   - values: 用户的价值观和信念（字符串数组，如["重视家庭", "环保意识强"]）
   - relationships: 用户的人际关系（字符串数组，如["妻子 Emily", "朋友 Tom"]）
   - personality: 用户的性格特征（字符串数组，如["外向", "乐观"]）"""

        return f"""分析以下对话，提取用户的记忆信息。请严格按照 JSON 格式返回结果。

对话内容：
```
{conversation}
```
{temporal_section}
请提取以下记忆：

1. **Facts（事实）**: 用户及对话中提到的人物的客观信息
   - 格式: {{"content": "事实描述", "category": "分类", "confidence": 0.0-1.0, "importance": 1-10, "entities": {{"people": [...], "locations": [...], "topics": [...]}}, "emotion": {{"valence": -1.0~1.0, "arousal": 0.0~1.0, "label": "情感描述"}} 或 null}}
   - category 可选: work, skill, hobby, personal, education, location, health, relationship, finance
   - importance: 对用户的重要程度（1=随口一提, 5=日常信息, 9=非常重要如生日/重大事件, 10=核心身份信息）
   - emotion: 标注该事实相关的情感基调。大多数对话都带有情感色彩（积极/消极/中性），请尽量标注。仅当内容完全是客观事实（如"用户住在北京"）时才设为 null
   - entities: 提取该事实中提到的人名、地点和关键主题

   **Facts 关键规则**:
   - Facts 只捕获**持久、可复用的属性**：职业、爱好、技能、性格、关系、价值观、偏好等
   - 一次性事件（"昨天去了X"、"上周做了Y"）应放入 Episodes，**不要**同时作为 Fact 重复。若该事件揭示了持久特征，提取推断出的属性（如"用户喜欢古典音乐"），而非复述事件本身
   - 错误示范: "用户去悉尼歌剧院听贝多芬交响乐"（一次性事件，应放 Episodes）
   - 正确示范: "用户喜欢古典音乐" 或 "用户对贝多芬感兴趣"（从事件推断的持久偏好）
   - **保留具体细节**：提取兴趣/爱好/偏好时，必须保留用户提到的**具体内容**，不要泛化成宽泛类别
     - 错误: "用户喜欢户外活动"（太笼统，丢失所有细节）
     - 正确: "用户喜欢恐龙和大自然"（保留具体话题）
     - 错误: "用户喜欢绘画"（丢失了画什么）
     - 正确: "用户喜欢画日落风景"（保留具体内容）
     - 规则：如果用户提到了具体的事物（动物、地点、话题等），必须在 fact 中明确写出
   - 每个 fact 必须是原子的：一条 fact 只包含一个独立信息
   - 每个 fact 必须有明确的主语（禁止使用代词如"他/她/它"）
   - 必须将代词还原为实际名称："她在那里工作" → "Caroline 在心理咨询中心工作"
   - 错误示范: "Caroline 是跨性别者，在咨询中心工作"（两个事实合并了）
   - 正确示范: "Caroline 是跨性别女性" + "Caroline 在心理咨询中心工作"（分开的原子事实）
   - 错误示范: "她喜欢狗"（代词，不完整）
   - 正确示范: "用户喜欢狗" 或 "Caroline 喜欢狗"（明确主语）
   - 提取所有实体属性：姓名、年龄、职业、居住地、学历、人际关系、技能、兴趣、身份
   - 同时提取概念性/推理性信息：
     * 意图和计划："用户计划考取心理咨询师证书"
     * 兴趣和爱好："用户对心理学感兴趣"
     * 技能和能力："Caroline 精通西班牙语"
     * 价值观和信念："用户重视家庭支持"
     * 性格特征："用户性格内向"
     * 因果关系："用户因为新工作搬到了纽约"

2. **Episodes（情景）**: 事件、经历、时间相关信息
   - 格式: {{"content": "事件描述", "timestamp": "ISO日期或null", "timestamp_original": "原始时间表达或null", "people": ["人名1", "人名2"], "location": "地点或null", "confidence": 0.0-1.0, "importance": 1-10, "entities": {{"people": [...], "locations": [...], "topics": [...]}}, "emotion": {{"valence": -1.0~1.0, "arousal": 0.0~1.0, "label": "情感描述"}} 或 null}}
   - people: 事件中涉及的人物列表（不包括用户自己）
   - location: 事件发生的地点
   - timestamp: 尽可能计算为 ISO 8601 格式的绝对日期
   - timestamp_original: 对话中的原始时间表达（如"昨天"、"去年夏天"）
   - entities: 同 Facts
   - content 必须使用明确的名称，禁止代词

3. **注意事项**:
   - importance: 根据内容对用户生活的重要程度打分
   - emotion: 尽量标注情感基调（包括隐含的情感），仅完全客观无情感的内容才设为 null
   - 全文代词消解：将所有代词还原为实际名称
   - 提取对话中所有提到的人物的信息，不仅仅是用户自己
   - 同时提取具体事实和概念性/抽象信息（计划、兴趣、价值观、推理链）
{triples_section}

{profile_section_zh}

要求：
- 只提取明确提到的信息，不要推测
- confidence 表示提取的确信度 (0.0-1.0)
- 如果某类没有信息，返回空列表
- 必须返回有效的 JSON 格式，不要有其他文字说明
- **语言要求**：所有 content/value 字段必须使用对话的语言（中文对话用中文，英文对话用英文）。禁止为同一信息同时生成中英文版本，禁止翻译对话内容为其他语言。每条信息只输出一次。

返回格式（只返回 JSON，不要其他内容）：
```json
{{
  "facts": [...],
  "episodes": [...]{triples_output},
  "profile_updates": {{...}}
}}
```"""

    def _build_en_prompt(self, conversation: str, session_timestamp: str | None = None) -> str:
        """Build English classification prompt for English conversations."""
        triples_section = ""
        triples_output = ""
        profile_num = 4
        if self._graph_enabled:
            triples_section = """
4. **Triples (Entity-Relation Triples)**: Structured relationships extracted from Facts and Episodes
   - Format: {{"subject": "entity", "subject_type": "type", "relation": "relation", "object": "entity", "object_type": "type", "content": "original description", "confidence": 0.0-1.0}}
   - subject_type/object_type options: user, person, organization, location, skill, entity (**never use "concept"**)
   - **object MUST be a concrete, nameable real-world entity**: a specific person, place, organization, tool, skill, language, or concrete activity (e.g. "hiking", "chess")
   - **Do NOT** use abstract concepts, descriptive phrases, or emotions as object (e.g. "Beethoven's music", "stress", "a good life")
   - Facts relations (prefer these): works_at, lives_in, has_skill, studied_at, uses, knows, hobby, owns, speaks, born_in
   - Episodes relations: met (met someone), attended (attended event), visited (visited place), occurred_at (location)
   - For user's own: subject="user", subject_type="user"
   - Skip triples with confidence < 0.6
   - Only extract a triple when the object is a concrete entity — skip otherwise"""
            triples_output = ',\n  "triples": [...]'
            profile_num = 5

        temporal_section = ""
        if session_timestamp:
            temporal_section = f"""
**Temporal Context**:
   - Current conversation session time: {session_timestamp}
   - Convert ALL relative time expressions to absolute dates based on session time
   - Examples: "yesterday" → compute actual date, "last week" → compute date range, "3 years ago" → compute year
   - Store computed absolute time in the "timestamp" field as ISO 8601 format (e.g. "2023-05-06")
   - Also preserve the original expression in "timestamp_original" field
"""

        profile_section_en = f"""{profile_num}. **Profile Updates**: User profile information extracted from the conversation
   - Only include fields that are **explicitly mentioned** in the conversation. Omit fields with no information.
   - identity: User's name, age, gender, and other core identity info (string, e.g. "John Smith, male, 28 years old")
   - occupation: User's job title, company, role (string, e.g. "Software engineer at Google")
   - interests: User's hobbies and interests (string array, e.g. ["photography", "hiking"])
   - preferences: User's preferences and habits (string array, e.g. ["likes coffee", "prefers dark mode"])
   - values: User's values and beliefs (string array, e.g. ["values family", "environmentally conscious"])
   - relationships: User's interpersonal relationships (string array, e.g. ["wife Emily", "friend Tom"])
   - personality: User's personality traits (string array, e.g. ["extroverted", "optimistic"])"""

        return f"""Extract structured memory information from the following conversation. Return results strictly in JSON format.

Conversation:
```
{conversation}
```
{temporal_section}
Extract the following memories:

1. **Facts**: Objective information about the user and people mentioned
   - Format: {{"content": "fact description", "category": "category", "confidence": 0.0-1.0, "importance": 1-10, "entities": {{"people": [...], "locations": [...], "topics": [...]}}, "emotion": {{"valence": -1.0~1.0, "arousal": 0.0~1.0, "label": "emotion"}} or null}}
   - Category options: work, skill, hobby, personal, education, location, health, relationship, finance
   - Importance: significance to user's life (1=casual mention, 5=daily info, 9=very important like birthday/major events, 10=core identity)
   - Emotion: tag the emotional tone for this fact. Most conversations carry emotional undertones (positive/negative/neutral) — tag them. Only set null for purely objective facts like "User lives in Beijing"
   - entities: extract people names, locations, and key topics mentioned in this fact

   **CRITICAL rules for Facts**:
   - Facts capture only **persistent, reusable attributes**: occupation, hobbies, skills, personality, relationships, values, preferences, etc.
   - One-time events ("went to X yesterday", "did Y last week") belong in Episodes — do NOT duplicate them as Facts. If an event reveals a lasting trait, extract the inferred attribute (e.g. "The user enjoys classical music"), not a restatement of the event itself.
   - BAD: "The user went to Sydney Opera House to listen to Beethoven" (one-time event → put in Episodes)
   - GOOD: "The user enjoys classical music" or "The user is a fan of Beethoven" (persistent preference inferred from the event)
   - **PRESERVE SPECIFICS**: When extracting interests/hobbies/preferences, keep the SPECIFIC details. Do NOT abstract into generic categories.
     - BAD: "The user enjoys outdoor activities" — too vague, loses all detail
     - GOOD: "The user likes dinosaurs and nature" — specific topics preserved
     - BAD: "The user likes painting" — loses what they paint
     - GOOD: "The user likes painting sunsets" — specific subject preserved
     - Rule: if the user mentioned specific things (animals, places, topics, etc.), include them explicitly
   - Each fact MUST be atomic: one single piece of information per fact
   - Each fact MUST be self-contained with explicit subject (never use pronouns like "she/he/they")
   - Always resolve pronouns to actual names: "She works there" → "Caroline works at the counseling center"
   - BAD: "Caroline is transgender and works at a counseling center" (two facts merged)
   - GOOD: "Caroline is a transgender woman" + "Caroline works at a counseling center" (separate atomic facts)
   - BAD: "She likes dogs" (pronoun, incomplete)
   - GOOD: "The user likes dogs" or "Caroline likes dogs" (explicit subject)
   - Extract ALL entity attributes: name, age, occupation, location, education, relationships, skills, interests, identity
   - Also extract conceptual/inferential information:
     * Intentions and plans: "The user plans to get a counseling certification"
     * Interests and passions: "The user is interested in psychology"
     * Skills and abilities: "Caroline is fluent in Spanish"
     * Values and beliefs: "The user values family support"
     * Personality traits: "The user is introverted"
     * Causal relationships: "The user moved to NYC because of a new job"

2. **Episodes**: Events, experiences, temporal information
   - Format: {{"content": "event description", "timestamp": "ISO date or null", "timestamp_original": "original time expression or null", "people": ["person1", "person2"], "location": "place or null", "confidence": 0.0-1.0, "importance": 1-10, "entities": {{"people": [...], "locations": [...], "topics": [...]}}, "emotion": {{"valence": -1.0~1.0, "arousal": 0.0~1.0, "label": "emotion"}} or null}}
   - people: List of people involved in the event (excluding the user)
   - location: Where the event occurred
   - timestamp: Computed absolute date in ISO 8601 format when possible
   - timestamp_original: The original time expression from the conversation (e.g. "yesterday", "last summer")
   - entities: same as Facts
   - content MUST use explicit names, never pronouns

3. **Guidelines**:
   - Importance: rate based on significance to user's life
   - Emotion: tag emotional tone including implicit sentiment. Only set null for purely objective content
   - Resolve ALL pronoun references to actual names throughout
   - Extract facts about ALL people mentioned, not just the user
   - Extract both concrete facts AND conceptual/abstract information (plans, interests, values, reasoning)
{triples_section}

{profile_section_en}

Requirements:
- Only extract explicitly mentioned information, do not infer
- Confidence represents extraction certainty (0.0-1.0)
- Return empty list if no information for a category
- Must return valid JSON format only, no additional text
- **Language rule**: All content/value fields MUST use the same language as the conversation. Do NOT produce bilingual or translated duplicates. Each piece of information should appear exactly once, in the conversation's language.

Return format (JSON only, no other content):
```json
{{
  "facts": [...],
  "episodes": [...]{triples_output},
  "profile_updates": {{...}}
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

            facts = result.get("facts", [])
            episodes = result.get("episodes", [])
            triples = result.get("triples", [])

            if not isinstance(facts, list):
                facts = []
            if not isinstance(episodes, list):
                episodes = []
            if not isinstance(triples, list):
                triples = []

            profile_updates = result.get("profile_updates", {})
            if not isinstance(profile_updates, dict):
                profile_updates = {}

            return {
                "facts": facts,
                "episodes": episodes,
                "triples": triples,
                "profile_updates": profile_updates,
            }

        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON from classification result: %s", e)
            return {"facts": [], "episodes": [], "triples": [], "profile_updates": {}}
        except Exception as e:
            logger.error("Error parsing classification result: %s", e)
            return {"facts": [], "episodes": [], "triples": [], "profile_updates": {}}

    def _resolve_timestamp(
        self,
        llm_timestamp: str | None,
        timestamp_original: str | None,
        content: str,
        ref_time: datetime | None,
    ) -> datetime | None:
        """Three-level timestamp resolution.

        1. LLM returned a valid ISO date -> use directly
        2. LLM returned raw text (e.g. "yesterday") -> TemporalExtractor converts
        3. Nothing from LLM -> TemporalExtractor tries content text
        """
        # Level 1: LLM returned valid ISO date
        if llm_timestamp:
            try:
                dt = datetime.fromisoformat(llm_timestamp)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                # Not a valid ISO date, try as text in level 2
                result = self._temporal.extract(llm_timestamp, ref_time)
                if result:
                    return result

        # Level 2: LLM returned original text expression
        if timestamp_original:
            result = self._temporal.extract(timestamp_original, ref_time)
            if result:
                return result

        # Level 3: Try extracting from content text
        result = self._temporal.extract(content, ref_time)
        if result:
            return result

        # Level 4: Fall back to session reference time so every memory has a timestamp
        return ref_time

    async def _store_facts(
        self,
        user_id: str,
        facts: list[dict],
        ref_time: datetime | None = None,
        pre_vectors: list | None = None,
    ) -> int:
        # Filter valid facts (caller may have already filtered, but guard anyway)
        valid_facts = [f for f in facts if f.get("content")]
        if not valid_facts:
            return 0

        if pre_vectors:
            vectors = pre_vectors
        else:
            # Fallback: compute embeddings if not pre-provided
            try:
                vectors = await self._embedding.embed_batch([f["content"] for f in valid_facts])
            except Exception as e:
                logger.error("Failed to batch embed facts: %s", e, exc_info=True)
                return 0

        if not vectors:
            return 0

        count = 0
        for fact, embedding_vector in zip(valid_facts, vectors):
            try:
                content = fact["content"]
                category = fact.get("category", "general")
                confidence = fact.get("confidence", 1.0)
                importance = fact.get("importance")
                emotion = fact.get("emotion")
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
                entities = fact.get("entities")
                if entities and isinstance(entities, dict):
                    meta["entities"] = entities

                # Resolve timestamp for facts (some facts have temporal info)
                resolved_ts = self._resolve_timestamp(
                    fact.get("timestamp"),
                    fact.get("timestamp_original"),
                    content,
                    ref_time,
                )

                embedding_obj = Embedding(
                    user_id=user_id,
                    content=content,
                    embedding=embedding_vector,
                    memory_type="fact",
                    metadata_=meta,
                    extracted_timestamp=resolved_ts,
                    valid_from=datetime.now(timezone.utc),
                )
                self.db.add(embedding_obj)
                count += 1
            except Exception as e:
                logger.error("Failed to store fact: %s", e, exc_info=True)

        return count

    async def _store_episodes(
        self,
        user_id: str,
        episodes: list[dict],
        ref_time: datetime | None = None,
        pre_vectors: list | None = None,
    ) -> int:
        # Filter valid episodes (caller may have already filtered, but guard anyway)
        valid_episodes = [e for e in episodes if e.get("content")]
        if not valid_episodes:
            return 0

        if pre_vectors:
            vectors = pre_vectors
        else:
            # Fallback: compute embeddings if not pre-provided
            try:
                vectors = await self._embedding.embed_batch([e["content"] for e in valid_episodes])
            except Exception as e:
                logger.error("Failed to batch embed episodes: %s", e, exc_info=True)
                return 0

        if not vectors:
            return 0

        count = 0
        for episode, embedding_vector in zip(valid_episodes, vectors):
            try:
                content = episode["content"]
                timestamp = episode.get("timestamp")
                timestamp_original = episode.get("timestamp_original")
                people = episode.get("people")
                location = episode.get("location")
                confidence = episode.get("confidence", 1.0)
                importance = episode.get("importance")
                emotion = episode.get("emotion")

                # Resolve timestamp using 3-level strategy
                resolved_ts = self._resolve_timestamp(
                    timestamp, timestamp_original, content, ref_time,
                )

                # Update metadata timestamp with resolved value
                meta_timestamp = timestamp
                if resolved_ts and not meta_timestamp:
                    meta_timestamp = resolved_ts.isoformat()

                meta = {
                    "timestamp": meta_timestamp,
                    "confidence": confidence,
                    "extracted_from": "conversation",
                }
                if timestamp_original:
                    meta["timestamp_original"] = timestamp_original
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
                entities = episode.get("entities")
                if entities and isinstance(entities, dict):
                    meta["entities"] = entities
                embedding_obj = Embedding(
                    user_id=user_id,
                    content=content,
                    embedding=embedding_vector,
                    memory_type="episodic",
                    metadata_=meta,
                    extracted_timestamp=resolved_ts,
                    valid_from=datetime.now(timezone.utc),
                )
                self.db.add(embedding_obj)
                count += 1
            except Exception as e:
                logger.error("Failed to store episode: %s", e, exc_info=True)

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

    # Keys that are overwritten each time (latest value wins)
    _PROFILE_OVERWRITE_KEYS = {"identity", "occupation"}
    # Keys that are append+dedup (accumulate over time)
    _PROFILE_APPEND_KEYS = {"interests", "values", "relationships", "personality", "preferences"}

    async def _store_profile_updates(
        self,
        user_id: str,
        profile_updates: dict,
    ) -> None:
        """Store user profile updates to KV store.

        - identity, occupation: overwrite (string)
        - interests, values, relationships, personality, preferences: append+dedup (list)

        Uses 1 batch-read + 1 batch-write instead of N sequential get/set pairs.
        """
        kv_service = KVService(self.db)

        # Filter to valid keys only
        valid_keys = self._PROFILE_OVERWRITE_KEYS | self._PROFILE_APPEND_KEYS
        valid_updates = {k: v for k, v in profile_updates.items() if k in valid_keys and v}
        if not valid_updates:
            return

        # Batch-read all existing profile values in one query
        existing_items = await kv_service.list("profile", user_id)
        existing_profile: dict = {item.key: item.value for item in existing_items}

        # Compute merged values
        to_write: dict = {}
        for key, value in valid_updates.items():
            if key in self._PROFILE_OVERWRITE_KEYS:
                to_write[key] = value
            else:
                # Append + dedup for list fields
                new_items = value if isinstance(value, list) else [value]
                new_items = [item for item in new_items if item]
                if not new_items:
                    continue
                existing = existing_profile.get(key)
                if existing and isinstance(existing, list):
                    seen = {item.lower() for item in existing}
                    merged = list(existing)
                    for item in new_items:
                        if item.lower() not in seen:
                            seen.add(item.lower())
                            merged.append(item)
                    to_write[key] = merged
                else:
                    to_write[key] = new_items

        # Single batch write
        if to_write:
            await kv_service.batch_set("profile", user_id, to_write)
