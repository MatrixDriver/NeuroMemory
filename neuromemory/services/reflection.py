"""Reflection service - synthesize recent memories into higher-level insights."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from neuromemory.models.emotion_profile import EmotionProfile
from neuromemory.models.memory import Embedding
from neuromemory.providers.embedding import EmbeddingProvider
from neuromemory.providers.llm import LLMProvider

logger = logging.getLogger(__name__)


class ReflectionService:
    """Periodic reflection: synthesize recent memories into insights.

    Inspired by Generative Agents (Park et al. 2023) - generates higher-level
    understanding from accumulated memories.
    """

    def __init__(
        self,
        db: AsyncSession,
        embedding: EmbeddingProvider,
        llm: LLMProvider,
    ):
        self.db = db
        self._embedding = embedding
        self._llm = llm

    async def reflect(
        self,
        user_id: str,
        recent_memories: list[dict],
        existing_insights: Optional[list[dict]] = None,
    ) -> dict:
        """Generate reflections from recent memories.

        This method performs two types of reflection:
        1. Pattern/Summary insights → stored as embeddings (memory_type="insight")
        2. Emotion profile update → stored in emotion_profiles table

        Args:
            user_id: The user to reflect about.
            recent_memories: List of recent memory dicts (content, memory_type, metadata, etc.).
            existing_insights: Previously generated pattern/summary insights to avoid duplication.

        Returns:
            Dict with:
            - insights: [{"content": "...", "category": "pattern|summary", ...}]
            - emotion_profile: {"latest_state": "...", "valence_avg": ..., ...}
        """
        if not recent_memories:
            return {"insights": [], "emotion_profile": None}

        # 1. Generate pattern and summary insights
        insights = await self._generate_insights(
            user_id, recent_memories, existing_insights
        )

        # 2. Update emotion profile (latest_state + long-term traits)
        emotion_profile = await self._update_emotion_profile(user_id, recent_memories)

        return {
            "insights": insights,
            "emotion_profile": emotion_profile,
        }

    async def _generate_insights(
        self,
        user_id: str,
        recent_memories: list[dict],
        existing_insights: Optional[list[dict]] = None,
    ) -> list[dict]:
        """Generate pattern and summary insights (not emotion)."""
        prompt = self._build_insight_prompt(recent_memories, existing_insights)

        try:
            result_text = await self._llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2048,
            )
            insights = self._parse_insight_result(result_text)
        except Exception as e:
            logger.error("Insight generation LLM call failed: %s", e, exc_info=True)
            return []

        # Store insights with memory_type="insight"
        stored = []
        for insight in insights:
            content = insight.get("content")
            category = insight.get("category", "pattern")
            if not content or category not in ("pattern", "summary"):
                continue
            try:
                vector = await self._embedding.embed(content)
                embedding_obj = Embedding(
                    user_id=user_id,
                    content=content,
                    embedding=vector,
                    memory_type="insight",
                    metadata_={
                        "category": category,
                        "source_ids": insight.get("source_ids", []),
                        "importance": 8,  # Insights are inherently important
                    },
                )
                self.db.add(embedding_obj)
                stored.append(insight)
            except Exception as e:
                logger.error("Failed to store insight: %s", e)

        if stored:
            await self.db.commit()

        return stored

    async def _update_emotion_profile(
        self, user_id: str, recent_memories: list[dict]
    ) -> dict | None:
        """Update emotion profile: latest_state (recent) + long-term traits.

        Args:
            user_id: The user ID.
            recent_memories: Recent memories (should include emotion metadata).

        Returns:
            Dict with emotion profile data, or None if update failed.
        """
        # Extract emotion data from recent memories
        emotions = []
        source_ids = []
        for mem in recent_memories:
            mem_id = mem.get("id")
            meta = mem.get("metadata") or {}
            if "emotion" in meta and meta["emotion"]:
                em = meta["emotion"]
                valence = em.get("valence")
                arousal = em.get("arousal")
                if valence is not None and arousal is not None:
                    emotions.append({"valence": valence, "arousal": arousal})
                    if mem_id:
                        source_ids.append(mem_id)

        if not emotions:
            logger.info("No emotion data in recent memories, skipping emotion profile update")
            return None

        # Calculate aggregates
        valence_avg = sum(e["valence"] for e in emotions) / len(emotions)
        arousal_avg = sum(e["arousal"] for e in emotions) / len(emotions)

        # Generate natural language summary with LLM
        prompt = self._build_emotion_summary_prompt(recent_memories, emotions)
        try:
            result_text = await self._llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1024,
            )
            summary_data = self._parse_emotion_summary(result_text)
        except Exception as e:
            logger.error("Emotion summary LLM call failed: %s", e, exc_info=True)
            summary_data = {
                "latest_state": f"近期情绪平均 valence={valence_avg:.2f}",
                "dominant_emotions": {},
                "emotion_triggers": {},
            }

        # Update or create emotion_profile row
        stmt = select(EmotionProfile).where(EmotionProfile.user_id == user_id)
        result = await self.db.execute(stmt)
        profile = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if profile:
            # Update existing profile
            profile.latest_state = summary_data.get("latest_state")
            profile.latest_state_period = self._get_current_period()
            profile.latest_state_valence = valence_avg
            profile.latest_state_arousal = arousal_avg
            profile.latest_state_updated_at = now
            profile.valence_avg = valence_avg  # Simple: replace with recent avg
            profile.arousal_avg = arousal_avg
            profile.dominant_emotions = summary_data.get("dominant_emotions")
            profile.emotion_triggers = summary_data.get("emotion_triggers")
            profile.source_memory_ids = source_ids
            profile.source_count = len(source_ids)
            profile.updated_at = now
        else:
            # Create new profile
            profile = EmotionProfile(
                user_id=user_id,
                latest_state=summary_data.get("latest_state"),
                latest_state_period=self._get_current_period(),
                latest_state_valence=valence_avg,
                latest_state_arousal=arousal_avg,
                latest_state_updated_at=now,
                valence_avg=valence_avg,
                arousal_avg=arousal_avg,
                dominant_emotions=summary_data.get("dominant_emotions"),
                emotion_triggers=summary_data.get("emotion_triggers"),
                source_memory_ids=source_ids,
                source_count=len(source_ids),
            )
            self.db.add(profile)

        await self.db.commit()

        return {
            "latest_state": profile.latest_state,
            "latest_state_valence": profile.latest_state_valence,
            "valence_avg": profile.valence_avg,
            "dominant_emotions": profile.dominant_emotions,
        }

    def _build_insight_prompt(
        self,
        memories: list[dict],
        existing_insights: Optional[list[dict]] = None,
    ) -> str:
        """Build prompt for generating pattern and summary insights."""
        memory_lines = []
        for i, m in enumerate(memories):
            content = m.get("content", "")
            mtype = m.get("memory_type", "unknown")
            memory_lines.append(f"{i+1}. [{mtype}] {content}")

        memories_text = "\n".join(memory_lines)

        existing_text = ""
        if existing_insights:
            existing_lines = [f"- {ins.get('content', '')}" for ins in existing_insights]
            existing_text = f"""
已有的洞察（避免重复）：
{chr(10).join(existing_lines)}
"""

        return f"""你是一个记忆分析系统。请根据以下关于用户的记忆条目，生成高层次的行为模式和阶段总结洞察。

用户最近的记忆：
{memories_text}
{existing_text}
请生成 2-4 条洞察，每条洞察应该：
1. 综合多条记忆得出更深层的理解（而非复述单条记忆）
2. 分为以下类别之一：
   - pattern: 用户的行为模式或习惯（如"用户倾向于晚上工作"、"用户喜欢用 Python 而非 Java"）
   - summary: 对一段时间经历的总结（如"用户近期在准备跳槽"、"本周重点是学习新技术栈"）

要求：
- 只基于已有记忆推理，不要凭空捏造
- 避免与已有洞察重复
- 必须返回有效的 JSON 格式

返回格式（只返回 JSON，不要其他内容）：
```json
{{
  "insights": [
    {{
      "content": "洞察内容",
      "category": "pattern|summary",
      "source_ids": []
    }}
  ]
}}
```"""

    def _build_emotion_summary_prompt(
        self, memories: list[dict], emotions: list[dict]
    ) -> str:
        """Build prompt for generating emotion profile summary."""
        memory_lines = []
        for i, m in enumerate(memories):
            content = m.get("content", "")
            meta = m.get("metadata") or {}
            emotion_str = ""
            if "emotion" in meta and meta["emotion"]:
                em = meta["emotion"]
                label = em.get("label", "")
                valence = em.get("valence", 0)
                arousal = em.get("arousal", 0)
                if label:
                    emotion_str = f" [情感: {label}, valence={valence:.1f}, arousal={arousal:.1f}]"
            memory_lines.append(f"{i+1}. {content}{emotion_str}")

        memories_text = "\n".join(memory_lines)

        valence_avg = sum(e["valence"] for e in emotions) / len(emotions)
        arousal_avg = sum(e["arousal"] for e in emotions) / len(emotions)

        return f"""你是一个情感分析系统。请根据用户最近的记忆和情感标注，生成情感画像总结。

用户最近的记忆（含情感标注）：
{memories_text}

统计数据：
- 平均 valence: {valence_avg:.2f} (-1=负面, 1=正面)
- 平均 arousal: {arousal_avg:.2f} (0=平静, 1=兴奋)

请生成：
1. latest_state: 一句话总结用户近期的情感状态（如"最近工作压力大，情绪偏低落"）
2. dominant_emotions: 主要情感分布（如 {{"焦虑": 0.6, "疲惫": 0.3}}）
3. emotion_triggers: 话题-情感关联（如 {{"工作": {{"valence": -0.5}}, "技术": {{"valence": 0.7}}}}）

返回格式（只返回 JSON，不要其他内容）：
```json
{{
  "latest_state": "用户近期情感状态描述",
  "dominant_emotions": {{"情感1": 0.6, "情感2": 0.4}},
  "emotion_triggers": {{"话题1": {{"valence": -0.5}}, "话题2": {{"valence": 0.7}}}}
}}
```"""

    def _parse_insight_result(self, result_text: str) -> list[dict]:
        """Parse LLM insight generation output."""
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
                return []

            insights = result.get("insights", [])
            if not isinstance(insights, list):
                return []

            valid = []
            for ins in insights:
                if isinstance(ins, dict) and ins.get("content"):
                    valid.append({
                        "content": ins["content"],
                        "category": ins.get("category", "pattern"),
                        "source_ids": ins.get("source_ids", []),
                    })
            return valid

        except json.JSONDecodeError as e:
            logger.error("Failed to parse insight JSON: %s", e)
            return []
        except Exception as e:
            logger.error("Error parsing insight result: %s", e)
            return []

    def _parse_emotion_summary(self, result_text: str) -> dict:
        """Parse LLM emotion summary output."""
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
                return {
                    "latest_state": "近期情感状态",
                    "dominant_emotions": {},
                    "emotion_triggers": {},
                }

            return {
                "latest_state": result.get("latest_state", "近期情感状态"),
                "dominant_emotions": result.get("dominant_emotions", {}),
                "emotion_triggers": result.get("emotion_triggers", {}),
            }

        except json.JSONDecodeError as e:
            logger.error("Failed to parse emotion summary JSON: %s", e)
            return {
                "latest_state": "近期情感状态",
                "dominant_emotions": {},
                "emotion_triggers": {},
            }
        except Exception as e:
            logger.error("Error parsing emotion summary: %s", e)
            return {
                "latest_state": "近期情感状态",
                "dominant_emotions": {},
                "emotion_triggers": {},
            }

    def _get_current_period(self) -> str:
        """Get current time period identifier (e.g., '2026-W06')."""
        now = datetime.now(timezone.utc)
        # ISO week format: YYYY-WXX
        year, week, _ = now.isocalendar()
        return f"{year}-W{week:02d}"
