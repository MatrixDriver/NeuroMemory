"""Tests for the TraitEngine — trait lifecycle management.

Covers scenes S3 (trait generation), S4 (upgrade chain),
S5 (confidence model), and partial S6 (contradiction handling).
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from neuromem.models.memory import Memory
from neuromem.providers.embedding import EmbeddingProvider
from neuromem.providers.llm import LLMProvider
from neuromem.services.trait_engine import TraitEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _insert_memory(db_session, mock_embedding, **kwargs) -> Memory:
    """Insert a raw memory row for testing."""
    from neuromem.services.search import SearchService
    svc = SearchService(db_session, mock_embedding)
    defaults = {
        "user_id": "te_user",
        "content": f"test memory {uuid.uuid4().hex[:8]}",
        "memory_type": "fact",
        "metadata": {"importance": 5},
    }
    defaults.update(kwargs)
    record = await svc.add_memory(**defaults)
    await db_session.commit()
    return record


async def _insert_trait(db_session, mock_embedding, **kwargs) -> Memory:
    """Insert a trait memory row directly via SearchService."""
    from neuromem.services.search import SearchService
    svc = SearchService(db_session, mock_embedding)

    # Separate trait-specific fields from add_memory params
    _TRAIT_FIELDS = {
        "trait_subtype", "trait_stage", "trait_confidence", "trait_context",
        "trait_derived_from", "trait_reinforcement_count", "trait_contradiction_count",
        "trait_last_reinforced", "trait_first_observed",
        "trait_window_start", "trait_window_end", "trait_parent_id",
    }
    add_kwargs = {k: v for k, v in kwargs.items() if k not in _TRAIT_FIELDS}

    defaults = {
        "user_id": "te_user",
        "content": f"trait {uuid.uuid4().hex[:8]}",
        "memory_type": "trait",
    }
    defaults.update(add_kwargs)
    record = await svc.add_memory(**defaults)
    # Set trait-specific columns directly
    record.trait_subtype = kwargs.get("trait_subtype", "behavior")
    record.trait_stage = kwargs.get("trait_stage", "candidate")
    record.trait_confidence = kwargs.get("trait_confidence", 0.4)
    record.trait_context = kwargs.get("trait_context", "general")
    record.trait_derived_from = kwargs.get("trait_derived_from", "reflection")
    record.trait_reinforcement_count = kwargs.get("trait_reinforcement_count", 0)
    record.trait_contradiction_count = kwargs.get("trait_contradiction_count", 0)
    if "trait_last_reinforced" in kwargs:
        record.trait_last_reinforced = kwargs["trait_last_reinforced"]
    if "trait_first_observed" in kwargs:
        record.trait_first_observed = kwargs["trait_first_observed"]
    if "trait_window_start" in kwargs:
        record.trait_window_start = kwargs["trait_window_start"]
    if "trait_window_end" in kwargs:
        record.trait_window_end = kwargs["trait_window_end"]
    if "trait_parent_id" in kwargs:
        record.trait_parent_id = kwargs["trait_parent_id"]
    db_session.add(record)
    await db_session.commit()
    return record


# ====================================================================
# S3: Trait Generation
# ====================================================================

class TestCreateTrend:
    """Tests for TraitEngine.create_trend()."""

    @pytest.mark.asyncio
    async def test_create_trend_basic(self, db_session, mock_embedding):
        """Trend 创建基本字段验证。"""
        engine = TraitEngine(db_session, mock_embedding)
        ev1 = await _insert_memory(db_session, mock_embedding, content="最近频繁讨论跳槽")
        ev2 = await _insert_memory(db_session, mock_embedding, content="更新了简历")

        trait = await engine.create_trend(
            user_id="te_user",
            content="近期关注职业变动",
            evidence_ids=[str(ev1.id), str(ev2.id)],
            window_days=30,
            context="work",
            cycle_id=str(uuid.uuid4()),
        )
        assert trait.memory_type == "trait"
        assert trait.trait_stage == "trend"
        assert trait.trait_subtype == "behavior"
        assert trait.trait_confidence is None  # trend 用 window 管理
        assert trait.trait_context == "work"
        assert trait.trait_derived_from == "reflection"
        assert trait.trait_window_start is not None
        assert trait.trait_window_end is not None
        # Window 长度约 30 天
        delta = trait.trait_window_end - trait.trait_window_start
        assert 29 <= delta.days <= 31

    @pytest.mark.asyncio
    async def test_create_trend_evidence_written(self, db_session, mock_embedding):
        """Trend 创建时 trait_evidence 表正确写入。"""
        engine = TraitEngine(db_session, mock_embedding)
        ev1 = await _insert_memory(db_session, mock_embedding, content="证据1")
        ev2 = await _insert_memory(db_session, mock_embedding, content="证据2")

        trait = await engine.create_trend(
            user_id="te_user",
            content="测试趋势",
            evidence_ids=[str(ev1.id), str(ev2.id)],
            window_days=30,
            context="general",
            cycle_id=str(uuid.uuid4()),
        )

        rows = await db_session.execute(
            text("SELECT trait_id, memory_id, evidence_type, quality FROM trait_evidence WHERE trait_id = :tid"),
            {"tid": str(trait.id)},
        )
        evidences = rows.fetchall()
        assert len(evidences) == 2
        for ev in evidences:
            assert ev.evidence_type == "supporting"

    @pytest.mark.asyncio
    async def test_create_trend_dedup_hash(self, db_session, mock_embedding):
        """content_hash 重复时强化而非新建。"""
        engine = TraitEngine(db_session, mock_embedding)
        ev1 = await _insert_memory(db_session, mock_embedding, content="证据A")

        t1 = await engine.create_trend(
            user_id="te_user",
            content="完全相同的趋势描述",
            evidence_ids=[str(ev1.id)],
            window_days=30,
            context="work",
            cycle_id=str(uuid.uuid4()),
        )

        ev2 = await _insert_memory(db_session, mock_embedding, content="证据B")
        t2 = await engine.create_trend(
            user_id="te_user",
            content="完全相同的趋势描述",
            evidence_ids=[str(ev2.id)],
            window_days=30,
            context="work",
            cycle_id=str(uuid.uuid4()),
        )
        # 应该返回同一个 trait（强化），不应新建
        assert str(t1.id) == str(t2.id)

    @pytest.mark.asyncio
    async def test_trend_window_custom(self, db_session, mock_embedding):
        """LLM 建议 14 天窗口时正确应用。"""
        engine = TraitEngine(db_session, mock_embedding)
        ev1 = await _insert_memory(db_session, mock_embedding, content="情绪证据")

        trait = await engine.create_trend(
            user_id="te_user",
            content="最近情绪波动",
            evidence_ids=[str(ev1.id)],
            window_days=14,
            context="personal",
            cycle_id=str(uuid.uuid4()),
        )
        delta = trait.trait_window_end - trait.trait_window_start
        assert 13 <= delta.days <= 15


class TestCreateBehavior:
    """Tests for TraitEngine.create_behavior()."""

    @pytest.mark.asyncio
    async def test_create_behavior_basic(self, db_session, mock_embedding):
        """Behavior 创建基本字段验证。"""
        engine = TraitEngine(db_session, mock_embedding)
        evs = []
        for i in range(3):
            evs.append(await _insert_memory(db_session, mock_embedding, content=f"行为证据{i}"))

        trait = await engine.create_behavior(
            user_id="te_user",
            content="深夜活跃",
            evidence_ids=[str(e.id) for e in evs],
            confidence=0.4,
            context="general",
            cycle_id=str(uuid.uuid4()),
        )
        assert trait.memory_type == "trait"
        assert trait.trait_stage == "candidate"
        assert trait.trait_subtype == "behavior"
        assert trait.trait_confidence == 0.4
        assert trait.trait_context == "general"
        assert trait.trait_first_observed is not None

    @pytest.mark.asyncio
    async def test_behavior_confidence_clamped(self, db_session, mock_embedding):
        """Behavior confidence clamp 在 [0.3, 0.5]。"""
        engine = TraitEngine(db_session, mock_embedding)
        ev = await _insert_memory(db_session, mock_embedding, content="证据")

        # confidence 过高应 clamp 到 0.5
        t1 = await engine.create_behavior(
            user_id="te_user",
            content="高置信行为",
            evidence_ids=[str(ev.id)],
            confidence=0.8,
            context="work",
            cycle_id=str(uuid.uuid4()),
        )
        assert t1.trait_confidence == 0.5

        # confidence 过低应 clamp 到 0.3
        ev2 = await _insert_memory(db_session, mock_embedding, content="证据2")
        t2 = await engine.create_behavior(
            user_id="te_user",
            content="低置信行为",
            evidence_ids=[str(ev2.id)],
            confidence=0.1,
            context="work",
            cycle_id=str(uuid.uuid4()),
        )
        assert t2.trait_confidence == 0.3

    @pytest.mark.asyncio
    async def test_trait_context_inferred(self, db_session, mock_embedding):
        """trait_context 按 LLM 推断正确赋值。"""
        engine = TraitEngine(db_session, mock_embedding)
        ev = await _insert_memory(db_session, mock_embedding, content="学习证据")

        trait = await engine.create_behavior(
            user_id="te_user",
            content="学习时偏好先看文档",
            evidence_ids=[str(ev.id)],
            confidence=0.4,
            context="learning",
            cycle_id=str(uuid.uuid4()),
        )
        assert trait.trait_context == "learning"


# ====================================================================
# S5: Confidence Model
# ====================================================================

class TestReinforcement:
    """Tests for TraitEngine.reinforce_trait()."""

    @pytest.mark.asyncio
    async def test_reinforce_grade_a(self, db_session, mock_embedding):
        """A 级跨情境证据：factor=0.25。"""
        engine = TraitEngine(db_session, mock_embedding)
        trait = await _insert_trait(db_session, mock_embedding, trait_confidence=0.4)
        ev = await _insert_memory(db_session, mock_embedding, content="跨情境证据")

        await engine.reinforce_trait(
            trait_id=str(trait.id),
            evidence_ids=[str(ev.id)],
            quality_grade="A",
            cycle_id=str(uuid.uuid4()),
        )
        await db_session.refresh(trait)
        expected = 0.4 + (1 - 0.4) * 0.25
        assert abs(trait.trait_confidence - expected) < 0.001

    @pytest.mark.asyncio
    async def test_reinforce_grade_b(self, db_session, mock_embedding):
        """B 级显式陈述：factor=0.20。"""
        engine = TraitEngine(db_session, mock_embedding)
        trait = await _insert_trait(db_session, mock_embedding, trait_confidence=0.4)
        ev = await _insert_memory(db_session, mock_embedding, content="显式陈述")

        await engine.reinforce_trait(
            trait_id=str(trait.id),
            evidence_ids=[str(ev.id)],
            quality_grade="B",
            cycle_id=str(uuid.uuid4()),
        )
        await db_session.refresh(trait)
        expected = 0.4 + (1 - 0.4) * 0.20
        assert abs(trait.trait_confidence - expected) < 0.001

    @pytest.mark.asyncio
    async def test_reinforce_grade_c(self, db_session, mock_embedding):
        """C 级跨对话：factor=0.15。"""
        engine = TraitEngine(db_session, mock_embedding)
        trait = await _insert_trait(db_session, mock_embedding, trait_confidence=0.4)
        ev = await _insert_memory(db_session, mock_embedding, content="跨对话证据")

        await engine.reinforce_trait(
            trait_id=str(trait.id),
            evidence_ids=[str(ev.id)],
            quality_grade="C",
            cycle_id=str(uuid.uuid4()),
        )
        await db_session.refresh(trait)
        expected = 0.4 + (1 - 0.4) * 0.15
        assert abs(trait.trait_confidence - expected) < 0.001

    @pytest.mark.asyncio
    async def test_reinforce_grade_d(self, db_session, mock_embedding):
        """D 级同对话：factor=0.05。"""
        engine = TraitEngine(db_session, mock_embedding)
        trait = await _insert_trait(db_session, mock_embedding, trait_confidence=0.4)
        ev = await _insert_memory(db_session, mock_embedding, content="同对话证据")

        await engine.reinforce_trait(
            trait_id=str(trait.id),
            evidence_ids=[str(ev.id)],
            quality_grade="D",
            cycle_id=str(uuid.uuid4()),
        )
        await db_session.refresh(trait)
        expected = 0.4 + (1 - 0.4) * 0.05
        assert abs(trait.trait_confidence - expected) < 0.001

    @pytest.mark.asyncio
    async def test_reinforce_updates_fields(self, db_session, mock_embedding):
        """强化更新 reinforcement_count, last_reinforced, confidence。"""
        engine = TraitEngine(db_session, mock_embedding)
        trait = await _insert_trait(db_session, mock_embedding, trait_confidence=0.4, trait_reinforcement_count=2)
        ev = await _insert_memory(db_session, mock_embedding, content="新证据")

        await engine.reinforce_trait(
            trait_id=str(trait.id),
            evidence_ids=[str(ev.id)],
            quality_grade="C",
            cycle_id=str(uuid.uuid4()),
        )
        await db_session.refresh(trait)
        assert trait.trait_reinforcement_count == 3
        assert trait.trait_last_reinforced is not None
        assert trait.trait_confidence > 0.4

    @pytest.mark.asyncio
    async def test_confidence_clamp(self, db_session, mock_embedding):
        """Confidence 始终 clamp 在 [0, 1]。"""
        engine = TraitEngine(db_session, mock_embedding)
        trait = await _insert_trait(db_session, mock_embedding, trait_confidence=0.99)
        ev = await _insert_memory(db_session, mock_embedding, content="证据")

        await engine.reinforce_trait(
            trait_id=str(trait.id),
            evidence_ids=[str(ev.id)],
            quality_grade="A",
            cycle_id=str(uuid.uuid4()),
        )
        await db_session.refresh(trait)
        assert 0 <= trait.trait_confidence <= 1.0


class TestContradiction:
    """Tests for TraitEngine.apply_contradiction()."""

    @pytest.mark.asyncio
    async def test_contradiction_single(self, db_session, mock_embedding):
        """单条矛盾：factor=0.2。"""
        engine = TraitEngine(db_session, mock_embedding)
        trait = await _insert_trait(db_session, mock_embedding, trait_confidence=0.5, trait_reinforcement_count=5)
        ev = await _insert_memory(db_session, mock_embedding, content="矛盾证据")

        result = await engine.apply_contradiction(
            trait_id=str(trait.id),
            evidence_ids=[str(ev.id)],
            cycle_id=str(uuid.uuid4()),
        )
        await db_session.refresh(trait)
        expected = 0.5 * (1 - 0.2)
        assert abs(trait.trait_confidence - expected) < 0.001
        assert trait.trait_contradiction_count == 1

    @pytest.mark.asyncio
    async def test_contradiction_multiple(self, db_session, mock_embedding):
        """多条矛盾：factor=0.4。"""
        engine = TraitEngine(db_session, mock_embedding)
        trait = await _insert_trait(db_session, mock_embedding, trait_confidence=0.5, trait_reinforcement_count=5)
        ev1 = await _insert_memory(db_session, mock_embedding, content="矛盾1")
        ev2 = await _insert_memory(db_session, mock_embedding, content="矛盾2")

        result = await engine.apply_contradiction(
            trait_id=str(trait.id),
            evidence_ids=[str(ev1.id), str(ev2.id)],
            cycle_id=str(uuid.uuid4()),
        )
        await db_session.refresh(trait)
        expected = 0.5 * (1 - 0.4)
        assert abs(trait.trait_confidence - expected) < 0.001
        assert trait.trait_contradiction_count == 2

    @pytest.mark.asyncio
    async def test_contradiction_evidence_written(self, db_session, mock_embedding):
        """矛盾证据写入 trait_evidence 表。"""
        engine = TraitEngine(db_session, mock_embedding)
        trait = await _insert_trait(db_session, mock_embedding, trait_confidence=0.5, trait_reinforcement_count=5)
        ev = await _insert_memory(db_session, mock_embedding, content="矛盾证据")

        await engine.apply_contradiction(
            trait_id=str(trait.id),
            evidence_ids=[str(ev.id)],
            cycle_id=str(uuid.uuid4()),
        )

        rows = await db_session.execute(
            text("SELECT evidence_type FROM trait_evidence WHERE trait_id = :tid AND evidence_type = 'contradicting'"),
            {"tid": str(trait.id)},
        )
        assert len(rows.fetchall()) == 1

    @pytest.mark.asyncio
    async def test_first_contradiction_no_reflection(self, db_session, mock_embedding):
        """首次矛盾 (count=1) 不触发专项反思，即使 ratio>0.3。"""
        engine = TraitEngine(db_session, mock_embedding)
        # reinforcement_count=1, contradiction_count=0 → 第一次矛盾后 count=1
        # ratio = 1/(1+1) = 0.5 > 0.3, 但 count=1 < 2
        trait = await _insert_trait(
            db_session, mock_embedding,
            trait_confidence=0.5,
            trait_reinforcement_count=1,
            trait_contradiction_count=0,
        )
        ev = await _insert_memory(db_session, mock_embedding, content="矛盾")

        result = await engine.apply_contradiction(
            trait_id=str(trait.id),
            evidence_ids=[str(ev.id)],
            cycle_id=str(uuid.uuid4()),
        )
        assert result.get("needs_special_reflection") is False

    @pytest.mark.asyncio
    async def test_contradiction_triggers_reflection(self, db_session, mock_embedding):
        """ratio > 0.3 且 count >= 2 时触发专项反思。"""
        engine = TraitEngine(db_session, mock_embedding)
        # reinforcement_count=3, contradiction_count=1 → 第二次矛盾后 count=2
        # ratio = 2/(3+2) = 0.4 > 0.3 且 count=2 >= 2
        trait = await _insert_trait(
            db_session, mock_embedding,
            trait_confidence=0.5,
            trait_reinforcement_count=3,
            trait_contradiction_count=1,
        )
        ev = await _insert_memory(db_session, mock_embedding, content="矛盾")

        result = await engine.apply_contradiction(
            trait_id=str(trait.id),
            evidence_ids=[str(ev.id)],
            cycle_id=str(uuid.uuid4()),
        )
        assert result.get("needs_special_reflection") is True

    @pytest.mark.asyncio
    async def test_contradiction_below_threshold(self, db_session, mock_embedding):
        """ratio <= 0.3 时不触发专项反思。"""
        engine = TraitEngine(db_session, mock_embedding)
        # reinforcement_count=10, contradiction_count=1 → 第二次矛盾后 count=2
        # ratio = 2/(10+2) = 0.167 < 0.3
        trait = await _insert_trait(
            db_session, mock_embedding,
            trait_confidence=0.5,
            trait_reinforcement_count=10,
            trait_contradiction_count=1,
        )
        ev = await _insert_memory(db_session, mock_embedding, content="矛盾")

        result = await engine.apply_contradiction(
            trait_id=str(trait.id),
            evidence_ids=[str(ev.id)],
            cycle_id=str(uuid.uuid4()),
        )
        assert result.get("needs_special_reflection") is False


# ====================================================================
# S5: Decay
# ====================================================================

class TestDecay:
    """Tests for TraitEngine.apply_decay()."""

    @pytest.mark.asyncio
    async def test_decay_behavior(self, db_session, mock_embedding):
        """Behavior lambda=0.005 衰减。"""
        engine = TraitEngine(db_session, mock_embedding)
        # 30 天前最后强化，reinforcement_count=1
        last_reinforced = datetime.now(timezone.utc) - timedelta(days=30)
        trait = await _insert_trait(
            db_session, mock_embedding,
            trait_confidence=0.5,
            trait_subtype="behavior",
            trait_stage="emerging",
            trait_reinforcement_count=1,
            trait_last_reinforced=last_reinforced,
        )

        await engine.apply_decay("te_user")
        await db_session.refresh(trait)

        effective_lambda = 0.005 / (1 + 0.1 * 1)
        expected = 0.5 * math.exp(-effective_lambda * 30)
        assert abs(trait.trait_confidence - expected) < 0.01

    @pytest.mark.asyncio
    async def test_decay_core_slow(self, db_session, mock_embedding):
        """Core lambda=0.001 衰减更慢。"""
        engine = TraitEngine(db_session, mock_embedding)
        last_reinforced = datetime.now(timezone.utc) - timedelta(days=30)
        trait = await _insert_trait(
            db_session, mock_embedding,
            trait_confidence=0.9,
            trait_subtype="core",
            trait_stage="core",
            trait_reinforcement_count=10,
            trait_last_reinforced=last_reinforced,
        )

        await engine.apply_decay("te_user")
        await db_session.refresh(trait)

        effective_lambda = 0.001 / (1 + 0.1 * 10)
        expected = 0.9 * math.exp(-effective_lambda * 30)
        assert abs(trait.trait_confidence - expected) < 0.01
        # core 衰减很慢，30 天后仍然很高
        assert trait.trait_confidence > 0.85

    @pytest.mark.asyncio
    async def test_decay_dissolved_threshold(self, db_session, mock_embedding):
        """衰减后 confidence < 0.1 → dissolved。"""
        engine = TraitEngine(db_session, mock_embedding)
        # 很久前的低 confidence，衰减后应该 dissolved
        last_reinforced = datetime.now(timezone.utc) - timedelta(days=365)
        trait = await _insert_trait(
            db_session, mock_embedding,
            trait_confidence=0.15,
            trait_subtype="behavior",
            trait_stage="candidate",
            trait_reinforcement_count=1,
            trait_last_reinforced=last_reinforced,
        )

        dissolved_count = await engine.apply_decay("te_user")
        await db_session.refresh(trait)
        assert trait.trait_stage == "dissolved"
        assert dissolved_count >= 1

    @pytest.mark.asyncio
    async def test_decay_spacing_effect(self, db_session, mock_embedding):
        """强化次数越多衰减越慢（间隔效应）。"""
        engine = TraitEngine(db_session, mock_embedding)
        last_reinforced = datetime.now(timezone.utc) - timedelta(days=60)

        # trait A：reinforcement_count=1
        trait_a = await _insert_trait(
            db_session, mock_embedding,
            content="少强化 trait",
            trait_confidence=0.5,
            trait_subtype="behavior",
            trait_stage="emerging",
            trait_reinforcement_count=1,
            trait_last_reinforced=last_reinforced,
        )

        # trait B：reinforcement_count=20
        trait_b = await _insert_trait(
            db_session, mock_embedding,
            content="多强化 trait",
            trait_confidence=0.5,
            trait_subtype="behavior",
            trait_stage="emerging",
            trait_reinforcement_count=20,
            trait_last_reinforced=last_reinforced,
        )

        await engine.apply_decay("te_user")
        await db_session.refresh(trait_a)
        await db_session.refresh(trait_b)
        # 多强化的 trait 衰减更慢
        assert trait_b.trait_confidence > trait_a.trait_confidence


# ====================================================================
# S5: Stage Auto-Transition
# ====================================================================

class TestStageTransition:
    """Tests for _update_stage logic."""

    @pytest.mark.asyncio
    async def test_stage_auto_transition(self, db_session, mock_embedding):
        """Confidence 区间自动流转阶段。"""
        engine = TraitEngine(db_session, mock_embedding)
        assert engine._update_stage(0.05) == "dissolved"
        assert engine._update_stage(0.2) == "candidate"
        assert engine._update_stage(0.3) == "emerging"
        assert engine._update_stage(0.5) == "emerging"
        assert engine._update_stage(0.6) == "established"
        assert engine._update_stage(0.8) == "established"
        assert engine._update_stage(0.85) == "core"
        assert engine._update_stage(0.95) == "core"

    @pytest.mark.asyncio
    async def test_stage_no_skip(self, db_session, mock_embedding):
        """Candidate (conf=0.7) 流转到 established 而非 core stage。"""
        engine = TraitEngine(db_session, mock_embedding)
        stage = engine._update_stage(0.7)
        assert stage == "established"


# ====================================================================
# S4: Upgrade Chain
# ====================================================================

class TestUpgradeChain:
    """Tests for TraitEngine.try_upgrade() and trend promotion."""

    @pytest.mark.asyncio
    async def test_trend_to_candidate(self, db_session, mock_embedding):
        """Trend 窗口内 >= 2 个 cycle 强化 → 升级 candidate。"""
        engine = TraitEngine(db_session, mock_embedding)
        now = datetime.now(timezone.utc)
        trait = await _insert_trait(
            db_session, mock_embedding,
            trait_stage="trend",
            trait_subtype="behavior",
            trait_confidence=None,
            trait_window_start=now - timedelta(days=10),
            trait_window_end=now + timedelta(days=20),
            trait_reinforcement_count=2,
        )

        promoted = await engine.promote_trends("te_user")
        await db_session.refresh(trait)
        assert promoted >= 1
        assert trait.trait_stage == "candidate"
        assert trait.trait_confidence == 0.3

    @pytest.mark.asyncio
    async def test_trend_expired_dissolved(self, db_session, mock_embedding):
        """窗口结束 + 强化 < 2 → dissolved。"""
        engine = TraitEngine(db_session, mock_embedding)
        now = datetime.now(timezone.utc)
        trait = await _insert_trait(
            db_session, mock_embedding,
            trait_stage="trend",
            trait_subtype="behavior",
            trait_confidence=None,
            trait_window_start=now - timedelta(days=40),
            trait_window_end=now - timedelta(days=10),
            trait_reinforcement_count=0,
        )

        expired = await engine.expire_trends("te_user")
        await db_session.refresh(trait)
        assert expired >= 1
        assert trait.trait_stage == "dissolved"

    @pytest.mark.asyncio
    async def test_behavior_to_preference(self, db_session, mock_embedding):
        """>= 2 behavior(conf>=0.5) 同倾向 → preference。"""
        engine = TraitEngine(db_session, mock_embedding)
        b1 = await _insert_trait(
            db_session, mock_embedding,
            content="决策前查数据",
            trait_subtype="behavior",
            trait_stage="emerging",
            trait_confidence=0.55,
        )
        b2 = await _insert_trait(
            db_session, mock_embedding,
            content="要求 AB 测试",
            trait_subtype="behavior",
            trait_stage="emerging",
            trait_confidence=0.52,
        )

        result = await engine.try_upgrade(
            from_trait_ids=[str(b1.id), str(b2.id)],
            new_content="数据驱动型决策者",
            new_subtype="preference",
            reasoning="两个行为指向同一倾向",
            cycle_id=str(uuid.uuid4()),
        )
        assert result is not None
        assert result.trait_subtype == "preference"
        assert result.trait_stage == "emerging"
        assert result.trait_confidence == pytest.approx(0.55 + 0.1, abs=0.01)

    @pytest.mark.asyncio
    async def test_preference_to_core(self, db_session, mock_embedding):
        """>= 2 preference(conf>=0.6) 同维度 → core。"""
        engine = TraitEngine(db_session, mock_embedding)
        p1 = await _insert_trait(
            db_session, mock_embedding,
            content="数据驱动决策",
            trait_subtype="preference",
            trait_stage="established",
            trait_confidence=0.65,
        )
        p2 = await _insert_trait(
            db_session, mock_embedding,
            content="注重流程规范",
            trait_subtype="preference",
            trait_stage="established",
            trait_confidence=0.70,
        )

        result = await engine.try_upgrade(
            from_trait_ids=[str(p1.id), str(p2.id)],
            new_content="高尽责性",
            new_subtype="core",
            reasoning="两个偏好指向同一人格维度",
            cycle_id=str(uuid.uuid4()),
        )
        assert result is not None
        assert result.trait_subtype == "core"
        assert result.trait_stage == "emerging"
        assert result.trait_confidence == pytest.approx(0.70 + 0.1, abs=0.01)

    @pytest.mark.asyncio
    async def test_upgrade_blocked_low_conf(self, db_session, mock_embedding):
        """Behavior confidence < 0.5 时不升级为 preference。"""
        engine = TraitEngine(db_session, mock_embedding)
        b1 = await _insert_trait(
            db_session, mock_embedding,
            content="低置信行为1",
            trait_subtype="behavior",
            trait_stage="candidate",
            trait_confidence=0.35,
        )
        b2 = await _insert_trait(
            db_session, mock_embedding,
            content="低置信行为2",
            trait_subtype="behavior",
            trait_stage="emerging",
            trait_confidence=0.45,
        )

        result = await engine.try_upgrade(
            from_trait_ids=[str(b1.id), str(b2.id)],
            new_content="不应升级",
            new_subtype="preference",
            reasoning="门槛不满足",
            cycle_id=str(uuid.uuid4()),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_upgrade_evidence_inherited(self, db_session, mock_embedding):
        """升级产物继承子 trait 的证据。"""
        engine = TraitEngine(db_session, mock_embedding)
        ev1 = await _insert_memory(db_session, mock_embedding, content="行为证据1")
        ev2 = await _insert_memory(db_session, mock_embedding, content="行为证据2")

        b1 = await _insert_trait(
            db_session, mock_embedding,
            content="行为1",
            trait_subtype="behavior",
            trait_stage="emerging",
            trait_confidence=0.55,
        )
        b2 = await _insert_trait(
            db_session, mock_embedding,
            content="行为2",
            trait_subtype="behavior",
            trait_stage="emerging",
            trait_confidence=0.5,
        )

        # 为子 trait 添加证据
        from neuromem.models.trait_evidence import TraitEvidence
        te1 = TraitEvidence(trait_id=b1.id, memory_id=ev1.id, evidence_type="supporting", quality="C")
        te2 = TraitEvidence(trait_id=b2.id, memory_id=ev2.id, evidence_type="supporting", quality="C")
        db_session.add_all([te1, te2])
        await db_session.commit()

        result = await engine.try_upgrade(
            from_trait_ids=[str(b1.id), str(b2.id)],
            new_content="偏好",
            new_subtype="preference",
            reasoning="test",
            cycle_id=str(uuid.uuid4()),
        )
        assert result is not None

        # 验证证据继承
        rows = await db_session.execute(
            text("SELECT COUNT(*) as cnt FROM trait_evidence WHERE trait_id = :tid"),
            {"tid": str(result.id)},
        )
        count = rows.scalar()
        assert count >= 2

    @pytest.mark.asyncio
    async def test_upgrade_stage_starts_emerging(self, db_session, mock_embedding):
        """升级产物 stage=emerging。"""
        engine = TraitEngine(db_session, mock_embedding)
        b1 = await _insert_trait(
            db_session, mock_embedding,
            trait_subtype="behavior",
            trait_stage="established",
            trait_confidence=0.7,
        )
        b2 = await _insert_trait(
            db_session, mock_embedding,
            trait_subtype="behavior",
            trait_stage="established",
            trait_confidence=0.6,
        )

        result = await engine.try_upgrade(
            from_trait_ids=[str(b1.id), str(b2.id)],
            new_content="偏好test",
            new_subtype="preference",
            reasoning="test",
            cycle_id=str(uuid.uuid4()),
        )
        assert result is not None
        assert result.trait_stage == "emerging"


# ====================================================================
# S6: Resolve Contradiction
# ====================================================================

class TestResolveContradiction:
    """Tests for TraitEngine.resolve_contradiction()."""

    class MockContradictionLLM(LLMProvider):
        """Mock LLM for contradiction resolution."""

        def __init__(self, response: str):
            self._response = response

        async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
            return self._response

    @pytest.mark.asyncio
    async def test_resolve_modify(self, db_session, mock_embedding):
        """专项反思决定修正 trait。"""
        engine = TraitEngine(db_session, mock_embedding)
        trait = await _insert_trait(
            db_session, mock_embedding,
            content="偏好独立工作",
            trait_confidence=0.5,
            trait_reinforcement_count=3,
            trait_contradiction_count=2,
        )

        mock_llm = self.MockContradictionLLM('{"action": "modify", "new_content": "偏好独立思考但享受团队讨论", "reasoning": "证据显示更细致的模式"}')

        result = await engine.resolve_contradiction(
            trait_id=str(trait.id),
            llm=mock_llm,
            cycle_id=str(uuid.uuid4()),
        )
        await db_session.refresh(trait)
        assert result["action"] == "modify"
        assert trait.content == "偏好独立思考但享受团队讨论"

    @pytest.mark.asyncio
    async def test_resolve_dissolve(self, db_session, mock_embedding):
        """专项反思决定废弃 trait。"""
        engine = TraitEngine(db_session, mock_embedding)
        trait = await _insert_trait(
            db_session, mock_embedding,
            content="不成立的 trait",
            trait_confidence=0.3,
            trait_reinforcement_count=2,
            trait_contradiction_count=3,
        )

        mock_llm = self.MockContradictionLLM('{"action": "dissolve", "reasoning": "矛盾太强"}')

        result = await engine.resolve_contradiction(
            trait_id=str(trait.id),
            llm=mock_llm,
            cycle_id=str(uuid.uuid4()),
        )
        await db_session.refresh(trait)
        assert result["action"] == "dissolve"
        assert trait.trait_stage == "dissolved"

    @pytest.mark.asyncio
    async def test_resolve_audit_trail(self, db_session, mock_embedding):
        """专项反思写入 memory_history 审计记录。"""
        engine = TraitEngine(db_session, mock_embedding)
        trait = await _insert_trait(
            db_session, mock_embedding,
            content="原始内容",
            trait_confidence=0.5,
            trait_reinforcement_count=3,
            trait_contradiction_count=2,
        )

        mock_llm = self.MockContradictionLLM('{"action": "modify", "new_content": "修改后内容", "reasoning": "test"}')

        await engine.resolve_contradiction(
            trait_id=str(trait.id),
            llm=mock_llm,
            cycle_id=str(uuid.uuid4()),
        )

        rows = await db_session.execute(
            text("SELECT event, old_content, new_content, actor FROM memory_history WHERE memory_id = :mid"),
            {"mid": str(trait.id)},
        )
        history = rows.fetchone()
        assert history is not None
        assert history.event == "contradiction_modify"
        assert history.old_content == "原始内容"
        assert history.new_content == "修改后内容"
        assert history.actor == "reflection"

    @pytest.mark.asyncio
    async def test_resolve_llm_failure_safe(self, db_session, mock_embedding):
        """专项反思 LLM 失败 → 保持现状。"""

        class FailingLLM(LLMProvider):
            async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
                raise RuntimeError("LLM service unavailable")

        engine = TraitEngine(db_session, mock_embedding)
        trait = await _insert_trait(
            db_session, mock_embedding,
            content="不应改变的 trait",
            trait_confidence=0.5,
            trait_stage="emerging",
        )

        result = await engine.resolve_contradiction(
            trait_id=str(trait.id),
            llm=FailingLLM(),
            cycle_id=str(uuid.uuid4()),
        )
        await db_session.refresh(trait)
        assert trait.content == "不应改变的 trait"
        assert trait.trait_stage == "emerging"
        assert trait.trait_confidence == 0.5
