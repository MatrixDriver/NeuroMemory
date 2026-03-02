"""Trait lifecycle management engine."""

from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from neuromem.models.memory import Memory
from neuromem.models.memory_history import MemoryHistory
from neuromem.models.trait_evidence import TraitEvidence
from neuromem.providers.embedding import EmbeddingProvider
from neuromem.providers.llm import LLMProvider

logger = logging.getLogger(__name__)

# Quality grade -> reinforcement factor mapping
_QUALITY_FACTORS = {"A": 0.25, "B": 0.20, "C": 0.15, "D": 0.05}

# Base decay lambda by subtype
_BASE_LAMBDA = {"behavior": 0.005, "preference": 0.002, "core": 0.001}

CONTRADICTION_PROMPT = """你是一个用户特质矛盾分析系统。请分析以下特质的矛盾情况并做出决策。

## 待分析特质
- 内容: {content}
- 子类型: {subtype}
- 当前置信度: {confidence:.2f}
- 情境: {context}

## 支持证据（{supporting_count} 条）
{supporting_list}

## 矛盾证据（{contradicting_count} 条）
{contradicting_list}

## 请分析并做出决策

决策选项：
1. **modify**: 原判断需要修正，更新特质描述。适用于：证据整体支持该倾向但描述不够精确
2. **dissolve**: 证据太弱或矛盾太强，该特质不成立。适用于：支持证据和矛盾证据势均力敌或矛盾占优

只返回 JSON，不要其他内容：
```json
{{
  "action": "modify" 或 "dissolve",
  "new_content": "修正后的特质描述（仅 modify 时需要）",
  "reasoning": "决策理由"
}}
```"""


class TraitEngine:
    """Manage trait lifecycle: creation, reinforcement, decay, upgrade, contradiction."""

    def __init__(self, db: AsyncSession, embedding: EmbeddingProvider):
        self.db = db
        self._embedding = embedding

    @staticmethod
    def _bump_version(trait: Memory) -> None:
        """Increment trait version for optimistic concurrency control."""
        trait.version = (trait.version or 1) + 1

    async def create_trend(
        self,
        user_id: str,
        content: str,
        evidence_ids: list[str],
        window_days: int,
        context: str,
        cycle_id: str,
    ) -> Memory | None:
        """Create a trend-stage trait. Returns None if content is sensitive."""
        from neuromem.services.reflection import is_sensitive_trait

        if is_sensitive_trait(content):
            logger.warning("Rejecting sensitive trend: %s", content[:60])
            return None

        content_hash = hashlib.md5(content.encode()).hexdigest()

        # Dedup check
        existing = await self._find_similar_trait(user_id, content, content_hash)
        if existing:
            logger.info("Trait dedup hit for trend: reinforcing %s", existing.id)
            valid_ids = await self._validate_evidence_ids(evidence_ids)
            if valid_ids:
                await self._write_evidence(existing.id, valid_ids, "supporting", "D", cycle_id)
            existing.trait_reinforcement_count = (existing.trait_reinforcement_count or 0) + len(valid_ids)
            existing.trait_last_reinforced = datetime.now(timezone.utc)
            self._bump_version(existing)
            await self.db.flush()
            return existing

        now = datetime.now(timezone.utc)
        embedding_vector = await self._embedding.embed(content)

        trait = Memory(
            user_id=user_id,
            content=content,
            embedding=embedding_vector,
            memory_type="trait",
            trait_stage="trend",
            trait_subtype="behavior",
            trait_window_start=now,
            trait_window_end=now + timedelta(days=window_days),
            trait_context=context,
            trait_derived_from="reflection",
            importance=0.5,
            content_hash=content_hash,
        )
        self.db.add(trait)
        await self.db.flush()

        # Write evidence
        valid_ids = await self._validate_evidence_ids(evidence_ids)
        if valid_ids:
            await self._write_evidence(trait.id, valid_ids, "supporting", "D", cycle_id)

        return trait

    async def create_behavior(
        self,
        user_id: str,
        content: str,
        evidence_ids: list[str],
        confidence: float,
        context: str,
        cycle_id: str,
        behavior_kind: str = "pattern",
    ) -> Memory | None:
        """Create a candidate-stage behavior trait. Returns None if content is sensitive."""
        from neuromem.services.reflection import is_sensitive_trait

        if is_sensitive_trait(content):
            logger.warning("Rejecting sensitive behavior: %s", content[:60])
            return None

        content_hash = hashlib.md5(content.encode()).hexdigest()

        # Dedup check
        existing = await self._find_similar_trait(user_id, content, content_hash)
        if existing:
            logger.info("Trait dedup hit for behavior: reinforcing %s", existing.id)
            valid_ids = await self._validate_evidence_ids(evidence_ids)
            if valid_ids:
                await self._write_evidence(existing.id, valid_ids, "supporting", "C", cycle_id)
            existing.trait_reinforcement_count = (existing.trait_reinforcement_count or 0) + len(valid_ids)
            existing.trait_last_reinforced = datetime.now(timezone.utc)
            self._bump_version(existing)
            await self.db.flush()
            return existing

        now = datetime.now(timezone.utc)
        embedding_vector = await self._embedding.embed(content)

        # Find earliest evidence time
        first_observed = now
        if evidence_ids:
            valid_ids = await self._validate_evidence_ids(evidence_ids)
            if valid_ids:
                result = await self.db.execute(
                    text("SELECT MIN(created_at) AS earliest FROM memories WHERE id = ANY(:ids)"),
                    {"ids": valid_ids},
                )
                row = result.first()
                if row and row.earliest:
                    first_observed = row.earliest
        else:
            valid_ids = []

        clamped_confidence = max(0.3, min(0.5, confidence))

        trait = Memory(
            user_id=user_id,
            content=content,
            embedding=embedding_vector,
            memory_type="trait",
            trait_stage="candidate",
            trait_subtype="behavior",
            trait_confidence=clamped_confidence,
            trait_context=context,
            trait_first_observed=first_observed,
            trait_derived_from="reflection",
            importance=0.5,
            content_hash=content_hash,
            metadata_={"behavior_kind": behavior_kind},
        )
        self.db.add(trait)
        await self.db.flush()

        # Write evidence
        if valid_ids:
            await self._write_evidence(trait.id, valid_ids, "supporting", "C", cycle_id)

        return trait

    async def reinforce_trait(
        self,
        trait_id: str,
        evidence_ids: list[str],
        quality_grade: str,
        cycle_id: str,
    ) -> None:
        """Reinforce a trait with new evidence."""
        result = await self.db.execute(
            select(Memory).where(Memory.id == trait_id, Memory.memory_type == "trait"),
        )
        trait = result.scalar_one_or_none()
        if not trait:
            logger.warning("reinforce_trait: trait %s not found", trait_id)
            return

        factor = _QUALITY_FACTORS.get(quality_grade, 0.15)
        old_confidence = trait.trait_confidence or 0.3
        new_confidence = old_confidence + (1 - old_confidence) * factor
        new_confidence = max(0.0, min(1.0, new_confidence))

        valid_ids = await self._validate_evidence_ids(evidence_ids)

        trait.trait_confidence = new_confidence
        trait.trait_reinforcement_count = (trait.trait_reinforcement_count or 0) + len(valid_ids)
        trait.trait_last_reinforced = datetime.now(timezone.utc)
        trait.trait_stage = self._update_stage(new_confidence)
        self._bump_version(trait)

        if valid_ids:
            await self._write_evidence(trait.id, valid_ids, "supporting", quality_grade, cycle_id)

        await self.db.flush()

    async def apply_contradiction(
        self,
        trait_id: str,
        evidence_ids: list[str],
        cycle_id: str,
    ) -> dict:
        """Apply contradicting evidence to a trait."""
        result = await self.db.execute(
            select(Memory).where(Memory.id == trait_id, Memory.memory_type == "trait"),
        )
        trait = result.scalar_one_or_none()
        if not trait:
            logger.warning("apply_contradiction: trait %s not found", trait_id)
            return {"needs_special_reflection": False, "trait_id": trait_id, "new_confidence": 0.0}

        valid_ids = await self._validate_evidence_ids(evidence_ids)

        old_confidence = trait.trait_confidence or 0.3
        # Single vs multiple contradiction
        if len(valid_ids) > 1:
            new_confidence = old_confidence * (1 - 0.4)
        else:
            new_confidence = old_confidence * (1 - 0.2)
        new_confidence = max(0.0, min(1.0, new_confidence))

        trait.trait_contradiction_count = (trait.trait_contradiction_count or 0) + len(valid_ids)
        trait.trait_confidence = new_confidence
        self._bump_version(trait)

        if valid_ids:
            await self._write_evidence(trait.id, valid_ids, "contradicting", "C", cycle_id)

        # Check if special reflection needed
        total = (trait.trait_reinforcement_count or 0) + (trait.trait_contradiction_count or 0)
        needs_special = False
        if total > 0:
            ratio = (trait.trait_contradiction_count or 0) / total
            needs_special = ratio > 0.3 and (trait.trait_contradiction_count or 0) >= 2

        await self.db.flush()

        return {
            "needs_special_reflection": needs_special,
            "trait_id": str(trait_id),
            "new_confidence": new_confidence,
        }

    async def try_upgrade(
        self,
        from_trait_ids: list[str],
        new_content: str,
        new_subtype: str,
        reasoning: str,
        cycle_id: str,
    ) -> Memory | None:
        """Try to upgrade traits to a higher subtype."""
        # Load source traits
        source_traits: list[Memory] = []
        for tid in from_trait_ids:
            result = await self.db.execute(
                select(Memory).where(Memory.id == tid, Memory.memory_type == "trait"),
            )
            trait = result.scalar_one_or_none()
            if trait:
                source_traits.append(trait)

        if not source_traits:
            logger.warning("try_upgrade: no valid source traits found")
            return None

        # Validate confidence thresholds
        if new_subtype == "preference":
            # behavior -> preference: each source behavior confidence >= 0.5
            for t in source_traits:
                if (t.trait_confidence or 0) < 0.5:
                    logger.info(
                        "try_upgrade: behavior %s confidence %.2f < 0.5, skipping",
                        t.id, t.trait_confidence or 0,
                    )
                    return None
        elif new_subtype == "core":
            # preference -> core: each source preference confidence >= 0.6
            for t in source_traits:
                if (t.trait_confidence or 0) < 0.6:
                    logger.info(
                        "try_upgrade: preference %s confidence %.2f < 0.6, skipping",
                        t.id, t.trait_confidence or 0,
                    )
                    return None

        # Circular reference check
        for t in source_traits:
            if t.trait_parent_id is not None:
                logger.warning("try_upgrade: trait %s already has parent, skipping", t.id)
                return None

        # Create new trait
        max_confidence = max((t.trait_confidence or 0) for t in source_traits)
        new_confidence = max(0.0, min(1.0, max_confidence + 0.1))

        embedding_vector = await self._embedding.embed(new_content)
        content_hash = hashlib.md5(new_content.encode()).hexdigest()

        new_trait = Memory(
            user_id=source_traits[0].user_id,
            content=new_content,
            embedding=embedding_vector,
            memory_type="trait",
            trait_stage="emerging",
            trait_subtype=new_subtype,
            trait_confidence=new_confidence,
            trait_context=source_traits[0].trait_context,
            trait_derived_from="reflection",
            importance=0.7,
            content_hash=content_hash,
        )
        self.db.add(new_trait)
        await self.db.flush()

        # Set parent references
        for t in source_traits:
            t.trait_parent_id = new_trait.id
            self._bump_version(t)

        # Inherit evidence from source traits
        for t in source_traits:
            result = await self.db.execute(
                select(TraitEvidence).where(TraitEvidence.trait_id == t.id),
            )
            for ev in result.scalars():
                new_ev = TraitEvidence(
                    trait_id=new_trait.id,
                    memory_id=ev.memory_id,
                    evidence_type=ev.evidence_type,
                    quality=ev.quality,
                )
                self.db.add(new_ev)

        await self.db.flush()

        logger.info(
            "try_upgrade: created %s (%s) from %d sources, confidence=%.2f",
            new_trait.id, new_subtype, len(source_traits), new_confidence,
        )
        return new_trait

    async def promote_trends(self, user_id: str) -> int:
        """Promote eligible trends to candidate stage."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(Memory).where(
                Memory.user_id == user_id,
                Memory.memory_type == "trait",
                Memory.trait_stage == "trend",
                Memory.trait_reinforcement_count >= 2,
                Memory.trait_window_end >= now,
            ),
        )
        traits = result.scalars().all()

        count = 0
        for trait in traits:
            trait.trait_stage = "candidate"
            trait.trait_confidence = 0.3
            trait.trait_window_start = None
            trait.trait_window_end = None
            self._bump_version(trait)
            count += 1

        if count:
            await self.db.flush()
            logger.info("promote_trends[%s]: promoted %d trends to candidate", user_id, count)

        return count

    async def expire_trends(self, user_id: str) -> int:
        """Expire trends that exceeded their observation window."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(Memory).where(
                Memory.user_id == user_id,
                Memory.memory_type == "trait",
                Memory.trait_stage == "trend",
                Memory.trait_window_end < now,
                Memory.trait_reinforcement_count < 2,
            ),
        )
        traits = result.scalars().all()

        count = 0
        for trait in traits:
            trait.trait_stage = "dissolved"
            trait.expired_at = now
            self._bump_version(trait)
            count += 1

        if count:
            await self.db.flush()
            logger.info("expire_trends[%s]: expired %d trends", user_id, count)

        return count

    async def apply_decay(self, user_id: str) -> int:
        """Apply time-based decay to all active non-trend traits."""
        result = await self.db.execute(
            select(Memory).where(
                Memory.user_id == user_id,
                Memory.memory_type == "trait",
                Memory.trait_stage.notin_(["trend", "dissolved"]),
            ),
        )
        traits = result.scalars().all()

        now = datetime.now(timezone.utc)
        dissolved_count = 0

        for trait in traits:
            last_reinforced = trait.trait_last_reinforced or trait.created_at
            if last_reinforced.tzinfo is None:
                last_reinforced = last_reinforced.replace(tzinfo=timezone.utc)

            days_since = (now - last_reinforced).total_seconds() / 86400
            if days_since <= 0:
                continue

            subtype = trait.trait_subtype or "behavior"
            base_lambda = _BASE_LAMBDA.get(subtype, 0.005)
            reinforcement_count = trait.trait_reinforcement_count or 0
            effective_lambda = base_lambda / (1 + 0.1 * reinforcement_count)

            old_confidence = trait.trait_confidence or 0.3
            new_confidence = old_confidence * math.exp(-effective_lambda * days_since)
            new_confidence = max(0.0, min(1.0, new_confidence))

            trait.trait_confidence = new_confidence

            if new_confidence < 0.1:
                trait.trait_stage = "dissolved"
                trait.expired_at = now
                dissolved_count += 1
            else:
                trait.trait_stage = self._update_stage(new_confidence)

            self._bump_version(trait)

        if traits:
            await self.db.flush()

        if dissolved_count:
            logger.info("apply_decay[%s]: dissolved %d traits", user_id, dissolved_count)

        return dissolved_count

    async def resolve_contradiction(
        self,
        trait_id: str,
        llm: LLMProvider,
        cycle_id: str,
    ) -> dict:
        """Run special reflection for a contradicted trait."""
        result = await self.db.execute(
            select(Memory).where(Memory.id == trait_id, Memory.memory_type == "trait"),
        )
        trait = result.scalar_one_or_none()
        if not trait:
            return {"action": "dissolve", "trait_id": str(trait_id)}

        # Load all evidence
        ev_result = await self.db.execute(
            select(TraitEvidence).where(TraitEvidence.trait_id == trait_id),
        )
        all_evidence = ev_result.scalars().all()

        supporting = [e for e in all_evidence if e.evidence_type == "supporting"]
        contradicting = [e for e in all_evidence if e.evidence_type == "contradicting"]

        # Load memory content for evidence
        supporting_list = await self._format_evidence_list(supporting)
        contradicting_list = await self._format_evidence_list(contradicting)

        prompt = CONTRADICTION_PROMPT.format(
            content=trait.content,
            subtype=trait.trait_subtype or "behavior",
            confidence=trait.trait_confidence or 0.0,
            context=trait.trait_context or "general",
            supporting_count=len(supporting),
            supporting_list=supporting_list,
            contradicting_count=len(contradicting),
            contradicting_list=contradicting_list,
        )

        try:
            result_text = await llm.chat(
                messages=[
                    {"role": "system", "content": "你是一个用户特质矛盾分析系统。只返回 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=1024,
            )
            parsed = self._parse_json(result_text)
        except Exception as e:
            logger.error("resolve_contradiction LLM failed: %s", e, exc_info=True)
            return {"action": "dissolve", "trait_id": str(trait_id)}

        action = parsed.get("action", "dissolve")
        now = datetime.now(timezone.utc)

        if action == "modify":
            old_content = trait.content
            new_content = parsed.get("new_content", trait.content)
            trait.content = new_content
            trait.trait_confidence = max(0.0, min(1.0, (trait.trait_confidence or 0.3) * 0.9))
            trait.trait_stage = self._update_stage(trait.trait_confidence)

            # Record history
            history = MemoryHistory(
                memory_id=trait.id,
                memory_type="trait",
                event="contradiction_modify",
                old_content=old_content,
                new_content=new_content,
                new_metadata={"reasoning": parsed.get("reasoning", "")},
                actor="reflection",
            )
            self.db.add(history)
        else:
            trait.trait_stage = "dissolved"
            trait.expired_at = now

            history = MemoryHistory(
                memory_id=trait.id,
                memory_type="trait",
                event="contradiction_dissolve",
                old_content=trait.content,
                new_metadata={"reasoning": parsed.get("reasoning", "")},
                actor="reflection",
            )
            self.db.add(history)

        self._bump_version(trait)
        await self.db.flush()

        return {"action": action, "trait_id": str(trait_id)}

    def _update_stage(self, confidence: float) -> str:
        """Determine trait stage based on confidence value."""
        if confidence < 0.1:
            return "dissolved"
        if confidence < 0.3:
            return "candidate"
        if confidence < 0.6:
            return "emerging"
        if confidence < 0.85:
            return "established"
        return "core"

    async def _find_similar_trait(
        self,
        user_id: str,
        content: str,
        content_hash: str,
    ) -> Memory | None:
        """Find an existing similar trait by hash or vector similarity."""
        # 1. Check content_hash exact match
        result = await self.db.execute(
            select(Memory).where(
                Memory.user_id == user_id,
                Memory.memory_type == "trait",
                Memory.content_hash == content_hash,
                Memory.trait_stage != "dissolved",
            ),
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        # 2. Check vector similarity > 0.95
        embedding_vector = await self._embedding.embed(content)
        vector_str = f"[{','.join(str(float(v)) for v in embedding_vector)}]"
        result = await self.db.execute(
            text(
                "SELECT id FROM memories "
                "WHERE user_id = :uid AND memory_type = 'trait' "
                "AND trait_stage != 'dissolved' "
                f"AND 1 - (embedding <=> '{vector_str}') > 0.95 "
                f"ORDER BY embedding <=> '{vector_str}' LIMIT 1"
            ),
            {"uid": user_id},
        )
        row = result.first()
        if row:
            result2 = await self.db.execute(
                select(Memory).where(Memory.id == row.id),
            )
            return result2.scalar_one_or_none()

        return None

    async def _validate_evidence_ids(self, evidence_ids: list[str]) -> list:
        """Validate that evidence IDs exist in the memories table."""
        if not evidence_ids:
            return []
        valid = []
        for eid in evidence_ids:
            try:
                result = await self.db.execute(
                    text("SELECT 1 FROM memories WHERE id = :id"),
                    {"id": eid},
                )
                if result.first():
                    valid.append(eid)
            except Exception:
                logger.debug("Invalid evidence_id: %s", eid)
        return valid

    async def _write_evidence(
        self,
        trait_id,
        evidence_ids: list,
        evidence_type: str,
        quality: str,
        cycle_id: str,
    ) -> None:
        """Write trait evidence records."""
        for eid in evidence_ids:
            ev = TraitEvidence(
                trait_id=trait_id,
                memory_id=eid,
                evidence_type=evidence_type,
                quality=quality,
            )
            self.db.add(ev)
        await self.db.flush()

    async def _format_evidence_list(self, evidence_records: list[TraitEvidence]) -> str:
        """Format evidence records into a readable list for LLM prompt."""
        if not evidence_records:
            return "(无)"
        lines = []
        for ev in evidence_records:
            result = await self.db.execute(
                select(Memory.content).where(Memory.id == ev.memory_id),
            )
            row = result.first()
            content = row.content if row else "(已删除)"
            lines.append(f"- [{ev.quality}] {content}")
        return "\n".join(lines)

    def _parse_json(self, result_text: str) -> dict:
        """Parse JSON from LLM response."""
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
            return json.loads(t)
        except (json.JSONDecodeError, Exception) as e:
            logger.error("Failed to parse JSON: %s", e)
            return {}
