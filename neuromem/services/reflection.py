"""Reflection service - 9-step reflection engine with trait lifecycle management."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from neuromem.models.conversation import ConversationSession
from neuromem.models.emotion_profile import EmotionProfile
from neuromem.models.memory import Memory
from neuromem.models.reflection_cycle import ReflectionCycle
from neuromem.providers.embedding import EmbeddingProvider
from neuromem.providers.llm import LLMProvider
from neuromem.services.trait_engine import TraitEngine

logger = logging.getLogger(__name__)

REFLECTION_PROMPT_TEMPLATE = """## 已有特质
{existing_traits_json}

## 新增记忆（自上次反思以来）
{new_memories_json}

## 分析任务

请严格按以下规则分析，返回 JSON 结果：

### 1. 短期趋势检测 (new_trends)
- 从新增记忆中识别**近期趋势**（证据跨度短、数量少的初步模式）
- 每条 trend 需要至少 2 条记忆支撑
- 为每条 trend 推断情境标签(context): work/personal/social/learning/general
- 建议观察窗口(window_days): 情绪相关趋势 14 天，其他 30 天

### 2. 行为模式检测 (new_behaviors)
- 从新增记忆中识别**行为模式**（≥3 条记忆呈现相同模式，或跨度较长）
- 与已有特质内容去重：如果某个模式已被已有特质覆盖，归入 reinforcements 而非 new_behaviors
- 为每条 behavior 推断情境标签(context)
- 初始置信度建议：通常 0.4，跨情境一致的可以给 0.5

### 3. 已有特质强化 (reinforcements)
- 检查新增记忆中是否有支持已有特质的证据
- 标注证据质量等级：
  - A: 跨情境行为一致性（同一模式在 work+personal 等不同情境中出现）
  - B: 用户显式自我陈述（"我是个急性子"）
  - C: 跨对话行为（不同对话中观测到相同模式）
  - D: 同对话内信号或隐式推断

### 4. 矛盾检测 (contradictions)
- 检查新增记忆中是否有**与已有特质矛盾**的证据
- 仅报告明确矛盾，不报告细微差异

### 5. 升级建议 (upgrades)
- 检查已有 behavior 是否有 ≥2 个指向同一倾向 → 建议升级为 preference
- 检查已有 preference 是否有 ≥2 个指向同一人格维度 → 建议升级为 core
- 注意：升级建议由代码层验证 confidence 门槛后执行

如果没有发现任何模式、强化或矛盾，返回所有数组为空的 JSON。

只返回 JSON，不要其他内容：
```json
{{
  "new_trends": [
    {{
      "content": "趋势描述（具体、有细节）",
      "evidence_ids": ["记忆ID1", "记忆ID2"],
      "window_days": 30,
      "context": "work"
    }}
  ],
  "new_behaviors": [
    {{
      "content": "行为模式描述",
      "evidence_ids": ["记忆ID1", "记忆ID2", "记忆ID3"],
      "confidence": 0.4,
      "context": "work"
    }}
  ],
  "reinforcements": [
    {{
      "trait_id": "已有特质的UUID",
      "new_evidence_ids": ["记忆ID"],
      "quality_grade": "C"
    }}
  ],
  "contradictions": [
    {{
      "trait_id": "已有特质的UUID",
      "contradicting_evidence_ids": ["记忆ID"],
      "description": "矛盾描述"
    }}
  ],
  "upgrades": [
    {{
      "from_trait_ids": ["behavior-id-1", "behavior-id-2"],
      "new_content": "升级后的描述",
      "new_subtype": "preference",
      "reasoning": "升级理由"
    }}
  ]
}}
```"""


class ReflectionService:
    """9-step reflection engine with trait lifecycle management.

    Replaces the original insight-based reflection with structured trait analysis.
    Preserves emotion profile update functionality.
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
        self._trait_engine = TraitEngine(db, embedding)

    async def should_reflect(self, user_id: str) -> tuple[bool, str | None, float | None]:
        """Check whether reflection should be triggered.

        Returns:
            (should_trigger, trigger_type, trigger_value)
        """
        # Query last_reflected_at from conversation_sessions
        result = await self.db.execute(
            sql_text(
                "SELECT last_reflected_at FROM conversation_sessions "
                "WHERE user_id = :uid ORDER BY last_reflected_at DESC NULLS LAST LIMIT 1"
            ),
            {"uid": user_id},
        )
        row = result.first()

        if not row or row.last_reflected_at is None:
            # Check if user has any memories at all
            mem_result = await self.db.execute(
                sql_text(
                    "SELECT COUNT(*) FROM memories "
                    "WHERE user_id = :uid AND memory_type IN ('fact', 'episodic')"
                ),
                {"uid": user_id},
            )
            mem_count = mem_result.scalar() or 0
            if mem_count == 0:
                return (False, None, None)
            return (True, "first_time", None)

        last_reflected = row.last_reflected_at
        now = datetime.now(timezone.utc)

        # Idempotency check: if last reflected within 60s, skip
        if (now - last_reflected).total_seconds() < 60:
            return (False, None, None)

        # Check importance accumulation
        # Use metadata importance as override when available (extraction sets it there),
        # fall back to the ORM importance column
        result = await self.db.execute(
            sql_text(
                "SELECT COALESCE(SUM(COALESCE((metadata->>'importance')::float, importance)), 0) AS total "
                "FROM memories "
                "WHERE user_id = :uid "
                "AND memory_type IN ('fact', 'episodic') "
                "AND created_at > :watermark"
            ),
            {"uid": user_id, "watermark": last_reflected},
        )
        accumulated = float(result.scalar() or 0)
        if accumulated >= 30:
            return (True, "importance_accumulated", accumulated)

        # Check 24h scheduled trigger
        if (now - last_reflected) >= timedelta(hours=24):
            return (True, "scheduled", None)

        # Check if there are any new memories at all
        result = await self.db.execute(
            sql_text(
                "SELECT COUNT(*) FROM memories "
                "WHERE user_id = :uid "
                "AND memory_type IN ('fact', 'episodic') "
                "AND created_at > :watermark"
            ),
            {"uid": user_id, "watermark": last_reflected},
        )
        new_count = result.scalar() or 0
        if new_count == 0:
            return (False, None, None)

        return (False, None, None)

    async def reflect(
        self,
        user_id: str,
        force: bool = False,
        session_ended: bool = False,
    ) -> dict:
        """Execute 9-step reflection pipeline.

        Args:
            user_id: User ID.
            force: Skip trigger check if True.
            session_ended: Mark as session-end trigger.

        Returns:
            Result dict with triggered, trigger_type, and stats.
        """
        # Step 0: Trigger check
        trigger_type: str | None = None
        trigger_value: float | None = None

        if session_ended:
            trigger_type = "session_end"
        elif force:
            trigger_type = "force"
        else:
            should, ttype, tvalue = await self.should_reflect(user_id)
            if not should:
                return {
                    "triggered": False,
                    "trigger_type": None,
                    "memories_scanned": 0,
                    "traits_created": 0,
                    "traits_updated": 0,
                    "traits_dissolved": 0,
                    "cycle_id": None,
                }
            trigger_type = ttype
            trigger_value = tvalue

        # Step 1: Create reflection cycle record
        cycle = ReflectionCycle(
            user_id=user_id,
            trigger_type=trigger_type or "unknown",
            trigger_value=trigger_value,
            status="running",
        )
        self.db.add(cycle)
        await self.db.flush()
        cycle_id = str(cycle.id)

        # Step 2: Run reflection steps
        try:
            stats = await self._run_reflection_steps(user_id, trigger_type, trigger_value, cycle_id)

            # Update cycle record
            cycle.status = "completed"
            cycle.completed_at = datetime.now(timezone.utc)
            cycle.memories_scanned = stats["memories_scanned"]
            cycle.traits_created = stats["traits_created"]
            cycle.traits_updated = stats["traits_updated"]
            cycle.traits_dissolved = stats["traits_dissolved"]
            await self.db.commit()

            return {
                "triggered": True,
                "trigger_type": trigger_type,
                "cycle_id": cycle_id,
                **stats,
            }

        except Exception as e:
            logger.error("Reflection failed for user=%s: %s", user_id, e, exc_info=True)
            cycle.status = "failed"
            cycle.completed_at = datetime.now(timezone.utc)
            cycle.error_message = str(e)[:500]
            await self.db.commit()

            return {
                "triggered": True,
                "trigger_type": trigger_type,
                "cycle_id": cycle_id,
                "memories_scanned": 0,
                "traits_created": 0,
                "traits_updated": 0,
                "traits_dissolved": 0,
                "error": str(e),
            }

    async def _run_reflection_steps(
        self,
        user_id: str,
        trigger_type: str | None,
        trigger_value: float | None,
        cycle_id: str,
    ) -> dict:
        """Core 9-step reflection pipeline."""
        stats = {"memories_scanned": 0, "traits_created": 0, "traits_updated": 0, "traits_dissolved": 0}

        # Step 1: Scan new memories
        new_memories = await self._scan_new_memories(user_id)
        stats["memories_scanned"] = len(new_memories)

        # Step 3 (before LLM): trend expiry/promotion (pure code)
        expired = await self._trait_engine.expire_trends(user_id)
        promoted = await self._trait_engine.promote_trends(user_id)
        stats["traits_dissolved"] += expired
        stats["traits_updated"] += promoted

        if not new_memories:
            # No new memories -> only apply decay
            dissolved = await self._trait_engine.apply_decay(user_id)
            stats["traits_dissolved"] += dissolved
            await self._update_watermark(user_id)
            return stats

        # Step 2: LLM main call
        existing_traits = await self._load_existing_traits(user_id)
        llm_result = await self._call_reflection_llm(new_memories, existing_traits)

        if llm_result is None:
            # LLM failed -> only apply decay, don't update watermark
            dissolved = await self._trait_engine.apply_decay(user_id)
            stats["traits_dissolved"] += dissolved
            return stats

        # Step 4: Process new_trends + new_behaviors
        for trend in llm_result.get("new_trends", []):
            await self._trait_engine.create_trend(
                user_id=user_id,
                content=trend["content"],
                evidence_ids=trend.get("evidence_ids", []),
                window_days=trend.get("window_days", 30),
                context=trend.get("context", "general"),
                cycle_id=cycle_id,
            )
            stats["traits_created"] += 1

        for behavior in llm_result.get("new_behaviors", []):
            await self._trait_engine.create_behavior(
                user_id=user_id,
                content=behavior["content"],
                evidence_ids=behavior.get("evidence_ids", []),
                confidence=behavior.get("confidence", 0.4),
                context=behavior.get("context", "general"),
                cycle_id=cycle_id,
            )
            stats["traits_created"] += 1

        # Step 5: Process reinforcements
        for reinforcement in llm_result.get("reinforcements", []):
            await self._trait_engine.reinforce_trait(
                trait_id=reinforcement["trait_id"],
                evidence_ids=reinforcement.get("new_evidence_ids", []),
                quality_grade=reinforcement.get("quality_grade", "C"),
                cycle_id=cycle_id,
            )
            stats["traits_updated"] += 1

        # Step 6: Process upgrades
        for upgrade in llm_result.get("upgrades", []):
            result = await self._trait_engine.try_upgrade(
                from_trait_ids=upgrade["from_trait_ids"],
                new_content=upgrade["new_content"],
                new_subtype=upgrade["new_subtype"],
                reasoning=upgrade.get("reasoning", ""),
                cycle_id=cycle_id,
            )
            if result:
                stats["traits_created"] += 1

        # Step 7: Process contradictions + possible special reflection
        for contradiction in llm_result.get("contradictions", []):
            result = await self._trait_engine.apply_contradiction(
                trait_id=contradiction["trait_id"],
                evidence_ids=contradiction.get("contradicting_evidence_ids", []),
                cycle_id=cycle_id,
            )
            if result.get("needs_special_reflection"):
                resolved = await self._trait_engine.resolve_contradiction(
                    trait_id=contradiction["trait_id"],
                    llm=self._llm,
                    cycle_id=cycle_id,
                )
                if resolved.get("action") == "dissolve":
                    stats["traits_dissolved"] += 1
                else:
                    stats["traits_updated"] += 1

        # Step 8: Time decay
        dissolved = await self._trait_engine.apply_decay(user_id)
        stats["traits_dissolved"] += dissolved

        # Step 9: Update watermark
        await self._update_watermark(user_id)

        return stats

    async def _scan_new_memories(self, user_id: str) -> list[dict]:
        """Scan memories created after last_reflected_at."""
        # Get watermark
        result = await self.db.execute(
            sql_text(
                "SELECT last_reflected_at FROM conversation_sessions "
                "WHERE user_id = :uid ORDER BY last_reflected_at DESC NULLS LAST LIMIT 1"
            ),
            {"uid": user_id},
        )
        row = result.first()
        watermark = row.last_reflected_at if row else None

        # Build query
        where = "user_id = :uid AND memory_type IN ('fact', 'episodic')"
        params: dict = {"uid": user_id}
        if watermark:
            where += " AND created_at > :watermark"
            params["watermark"] = watermark

        result = await self.db.execute(
            sql_text(
                f"SELECT id, content, memory_type, importance, metadata, created_at "
                f"FROM memories WHERE {where} "
                f"ORDER BY created_at ASC LIMIT 200"
            ),
            params,
        )
        rows = result.fetchall()

        return [
            {
                "id": str(r.id),
                "content": r.content,
                "memory_type": r.memory_type,
                "importance": float(r.importance) if r.importance else 0.5,
                "metadata": r.metadata,
                "created_at": str(r.created_at),
            }
            for r in rows
        ]

    async def _load_existing_traits(self, user_id: str) -> list[dict]:
        """Load existing active traits for LLM context."""
        result = await self.db.execute(
            sql_text(
                "SELECT id, content, trait_stage, trait_subtype, trait_confidence, trait_context "
                "FROM memories "
                "WHERE user_id = :uid AND memory_type = 'trait' "
                "AND trait_stage NOT IN ('dissolved') "
                "ORDER BY trait_confidence DESC NULLS LAST LIMIT 50"
            ),
            {"uid": user_id},
        )
        rows = result.fetchall()

        return [
            {
                "id": str(r.id),
                "content": r.content,
                "stage": r.trait_stage,
                "subtype": r.trait_subtype,
                "confidence": float(r.trait_confidence) if r.trait_confidence else 0.0,
                "context": r.trait_context,
            }
            for r in rows
        ]

    async def _call_reflection_llm(
        self,
        new_memories: list[dict],
        existing_traits: list[dict],
    ) -> dict | None:
        """Call LLM for main reflection analysis. Returns None on failure."""
        prompt = self._build_reflection_prompt(new_memories, existing_traits)
        try:
            result_text = await self._llm.chat(
                messages=[
                    {"role": "system", "content": "你是一个用户特质分析引擎。根据用户的新增记忆和已有特质，执行结构化分析。只返回 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=4096,
            )
            return self._parse_reflection_result(result_text)
        except Exception as e:
            logger.error("Reflection LLM call failed: %s", e, exc_info=True)
            return None

    def _build_reflection_prompt(
        self,
        new_memories: list[dict],
        existing_traits: list[dict],
    ) -> str:
        """Build the main reflection prompt."""
        existing_json = json.dumps(existing_traits, ensure_ascii=False, indent=2) if existing_traits else "[]"
        memories_json = json.dumps(
            [{"id": m["id"], "content": m["content"], "memory_type": m["memory_type"]} for m in new_memories],
            ensure_ascii=False,
            indent=2,
        )
        return REFLECTION_PROMPT_TEMPLATE.format(
            existing_traits_json=existing_json,
            new_memories_json=memories_json,
        )

    def _parse_reflection_result(self, result_text: str) -> dict | None:
        """Parse LLM reflection JSON response."""
        try:
            t = result_text.strip()
            if "```json" in t:
                start = t.find("```json") + 7
                end = t.find("```", start)
                t = t[start:end].strip()
            elif "```" in t:
                start = t.find("```") + 3
                end = t.find("```", start)
                t = t[start:end].strip()

            result = json.loads(t)
            if not isinstance(result, dict):
                return None
            return result
        except json.JSONDecodeError as e:
            logger.error("Failed to parse reflection JSON: %s", e)
            return None
        except Exception as e:
            logger.error("Error parsing reflection result: %s", e)
            return None

    async def _update_watermark(self, user_id: str) -> None:
        """Update conversation_sessions.last_reflected_at."""
        now = datetime.now(timezone.utc)
        # Try to update existing session
        result = await self.db.execute(
            sql_text(
                "UPDATE conversation_sessions SET last_reflected_at = :now "
                "WHERE user_id = :uid "
                "RETURNING id"
            ),
            {"uid": user_id, "now": now},
        )
        if result.first() is None:
            # No session exists for this user, create a minimal one
            await self.db.execute(
                sql_text(
                    "INSERT INTO conversation_sessions (user_id, session_id, last_reflected_at) "
                    "VALUES (:uid, :sid, :now) "
                    "ON CONFLICT (session_id) DO UPDATE SET last_reflected_at = EXCLUDED.last_reflected_at"
                ),
                {"uid": user_id, "sid": f"__reflect_{user_id}", "now": now},
            )

    # ============== Backward compatibility ==============

    async def digest(
        self,
        user_id: str,
        recent_memories: list[dict],
        existing_insights: Optional[list[dict]] = None,
    ) -> dict:
        """Backward-compatible digest entry point.

        Preserves the original digest() behavior:
        1. Generate pattern/summary insights via LLM and store as trait(trend)
        2. Update emotion profile

        Note: New code should use reflect() instead.
        """
        if not recent_memories:
            return {"insights": [], "emotion_profile": None}

        # 1. Generate pattern and summary insights (legacy behavior)
        insights = await self._generate_insights(user_id, recent_memories, existing_insights)

        # 2. Update emotion profile
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
        """Generate pattern and summary insights (legacy digest behavior)."""
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

        # Store insights with memory_type="trait", trait_stage="trend"
        _MIN_INSIGHT_IMPORTANCE = 7
        stored = []
        for insight in insights:
            content = insight.get("content")
            category = insight.get("category", "pattern")
            importance = int(insight.get("importance", 8))
            if not content or category not in ("pattern", "summary"):
                continue
            if importance < _MIN_INSIGHT_IMPORTANCE:
                logger.debug("Skipping low-importance insight (importance=%d): %s", importance, content[:60])
                continue
            try:
                vector = await self._embedding.embed(content)
                embedding_obj = Memory(
                    user_id=user_id,
                    content=content,
                    embedding=vector,
                    memory_type="trait",
                    trait_stage="trend",
                    metadata_={
                        "category": category,
                        "source_ids": insight.get("source_ids", []),
                        "importance": importance,
                    },
                )
                self.db.add(embedding_obj)
                stored.append(insight)
            except Exception as e:
                logger.error("Failed to store insight: %s", e)

        if stored:
            await self.db.commit()

        return stored

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
            recent = existing_insights[-20:]
            existing_lines = [f"- {ins.get('content', '')}" for ins in recent]
            existing_text = f"""
已有洞察（共 {len(existing_insights)} 条，显示最近 {len(recent)} 条）：
{chr(10).join(existing_lines)}

⚠️ 严格去重规则：
- 如果新洞察与已有洞察表达相同或相似的含义，直接跳过，不要输出
- 只输出已有洞察中**未覆盖**的新角度、新发现、或具体细节的补充
- 如果本批记忆没有带来新的洞察，返回空列表 {{"insights": []}}
"""

        return f"""你是一个记忆分析系统。根据用户的新记忆，生成**增量**行为模式和阶段总结洞察。

用户最新的记忆：
{memories_text}
{existing_text}
生成规则：
1. 每条洞察必须综合多条记忆，得出更深层的理解（不是复述单条记忆）
2. 类别：
   - pattern: 具体的行为模式或习惯（需有细节，如"用户在压力大时会回避社交，但之后主动寻求朋友帮助"）
   - summary: 近期经历的阶段性总结（需有时间感，如"用户近两周集中在解决技术债，已完成重构"）
3. importance（1-10）：对理解用户有多大价值
   - 9-10：揭示用户核心性格/价值观/重大转变
   - 7-8：有具体细节的有用模式
   - 5-6：泛泛的观察
   - <7：不要输出
4. 如果没有值得输出的新洞察，返回空列表

只返回 JSON，不要其他内容：
```json
{{
  "insights": [
    {{
      "content": "洞察内容（具体、有细节）",
      "category": "pattern|summary",
      "importance": 7,
      "source_ids": []
    }}
  ]
}}
```"""

    def _parse_insight_result(self, result_text: str) -> list[dict]:
        """Parse LLM insight generation output."""
        try:
            t = result_text.strip()

            if "```json" in t:
                start = t.find("```json") + 7
                end = t.find("```", start)
                t = t[start:end].strip()
            elif "```" in t:
                start = t.find("```") + 3
                end = t.find("```", start)
                t = t[start:end].strip()

            result = json.loads(t)

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

    # ============== Preserved methods (emotion profile) ==============

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
            profile.valence_avg = valence_avg
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

    def _parse_emotion_summary(self, result_text: str) -> dict:
        """Parse LLM emotion summary output."""
        try:
            t = result_text.strip()

            if "```json" in t:
                start = t.find("```json") + 7
                end = t.find("```", start)
                t = t[start:end].strip()
            elif "```" in t:
                start = t.find("```") + 3
                end = t.find("```", start)
                t = t[start:end].strip()

            result = json.loads(t)

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
        year, week, _ = now.isocalendar()
        return f"{year}-W{week:02d}"
