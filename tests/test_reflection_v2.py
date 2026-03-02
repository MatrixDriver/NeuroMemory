"""Tests for the new ReflectionService v2 — 9-step reflection engine.

Covers scenes S1 (trigger system), S2 (execution engine), and partial S6 (contradiction handling).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from neuromem.providers.embedding import EmbeddingProvider
from neuromem.providers.llm import LLMProvider
from neuromem.services.reflection import ReflectionService


# ---------------------------------------------------------------------------
# Mock LLM
# ---------------------------------------------------------------------------

class MockReflectionLLM(LLMProvider):
    """Mock LLM that returns predictable reflection results."""

    def __init__(self, main_response: str = "", contradiction_response: str = "", emotion_response: str = ""):
        self._main_response = main_response
        self._contradiction_response = contradiction_response
        self._emotion_response = emotion_response
        self._call_count = 0
        self.call_history: list[list[dict]] = []

    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        self._call_count += 1
        self.call_history.append(messages)
        if self._call_count == 1:
            return self._main_response
        elif self._call_count == 2 and self._contradiction_response:
            return self._contradiction_response
        return self._emotion_response or '{"latest_state": "", "dominant_emotions": {}, "emotion_triggers": {}}'


EMPTY_LLM_RESPONSE = json.dumps({
    "new_trends": [],
    "new_behaviors": [],
    "reinforcements": [],
    "contradictions": [],
    "upgrades": [],
})

SIMPLE_TREND_RESPONSE = json.dumps({
    "new_trends": [
        {
            "content": "最近频繁讨论职业发展",
            "evidence_ids": [],
            "window_days": 30,
            "context": "work",
        }
    ],
    "new_behaviors": [],
    "reinforcements": [],
    "contradictions": [],
    "upgrades": [],
})

SIMPLE_BEHAVIOR_RESPONSE = json.dumps({
    "new_trends": [],
    "new_behaviors": [
        {
            "content": "深夜活跃",
            "evidence_ids": [],
            "confidence": 0.4,
            "context": "personal",
        }
    ],
    "reinforcements": [],
    "contradictions": [],
    "upgrades": [],
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _insert_memories(db_session, mock_embedding, count=5, user_id="ref_user", importance=7):
    """Insert fact memories for testing."""
    from neuromem.services.search import SearchService
    svc = SearchService(db_session, mock_embedding)
    memories = []
    for i in range(count):
        m = await svc.add_memory(
            user_id=user_id,
            content=f"测试事实 {i} {uuid.uuid4().hex[:6]}",
            memory_type="fact",
            metadata={"importance": importance},
        )
        memories.append(m)
    await db_session.commit()
    return memories


async def _ensure_session(db_session, user_id="ref_user", last_reflected_at=None):
    """Ensure a watermark exists for the user in reflection_cycles."""
    if last_reflected_at is not None:
        from neuromem.models.reflection_cycle import ReflectionCycle
        cycle = ReflectionCycle(
            user_id=user_id,
            trigger_type="test_setup",
            status="completed",
            completed_at=last_reflected_at,
        )
        db_session.add(cycle)
        await db_session.commit()
        return cycle
    return None


# ====================================================================
# S1: Reflection Trigger System
# ====================================================================

class TestShouldReflect:
    """Tests for ReflectionService.should_reflect()."""

    @pytest.mark.asyncio
    async def test_should_reflect_first_time(self, db_session, mock_embedding, mock_llm):
        """last_reflected_at 为 NULL → 首次反思触发。"""
        await _ensure_session(db_session, last_reflected_at=None)
        await _insert_memories(db_session, mock_embedding, count=1)

        svc = ReflectionService(db_session, mock_embedding, mock_llm)
        should, trigger_type, _ = await svc.should_reflect("ref_user")
        assert should is True
        assert trigger_type == "first_time"

    @pytest.mark.asyncio
    async def test_should_reflect_importance_threshold(self, db_session, mock_embedding, mock_llm):
        """新记忆 importance 累积 >= 30 时触发。"""
        old_time = datetime.now(timezone.utc) - timedelta(hours=1)
        await _ensure_session(db_session, last_reflected_at=old_time)
        # importance=7, count=5 → 累积 35 >= 30
        await _insert_memories(db_session, mock_embedding, count=5, importance=7)

        svc = ReflectionService(db_session, mock_embedding, mock_llm)
        should, trigger_type, trigger_value = await svc.should_reflect("ref_user")
        assert should is True
        assert trigger_type == "importance_accumulated"
        assert trigger_value >= 30

    @pytest.mark.asyncio
    async def test_should_reflect_below_threshold(self, db_session, mock_embedding, mock_llm):
        """累积 < 30 且距上次 < 24h → 不触发。"""
        old_time = datetime.now(timezone.utc) - timedelta(hours=1)
        await _ensure_session(db_session, last_reflected_at=old_time)
        # importance=2, count=2 → 累积 4 < 30
        await _insert_memories(db_session, mock_embedding, count=2, importance=2)

        svc = ReflectionService(db_session, mock_embedding, mock_llm)
        should, _, _ = await svc.should_reflect("ref_user")
        assert should is False

    @pytest.mark.asyncio
    async def test_should_reflect_time_trigger(self, db_session, mock_embedding, mock_llm):
        """距上次反思 >= 24h 触发。"""
        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        await _ensure_session(db_session, last_reflected_at=old_time)
        await _insert_memories(db_session, mock_embedding, count=1, importance=1)

        svc = ReflectionService(db_session, mock_embedding, mock_llm)
        should, trigger_type, _ = await svc.should_reflect("ref_user")
        assert should is True
        assert trigger_type == "scheduled"

    @pytest.mark.asyncio
    async def test_should_reflect_idempotent_60s(self, db_session, mock_embedding, mock_llm):
        """last_reflected_at 在 60s 内时不触发（幂等）。"""
        recent = datetime.now(timezone.utc) - timedelta(seconds=30)
        await _ensure_session(db_session, last_reflected_at=recent)
        await _insert_memories(db_session, mock_embedding, count=10, importance=10)

        svc = ReflectionService(db_session, mock_embedding, mock_llm)
        should, _, _ = await svc.should_reflect("ref_user")
        assert should is False


# ====================================================================
# S2: Reflection Execution Engine
# ====================================================================

class TestReflect:
    """Tests for ReflectionService.reflect()."""

    @pytest.mark.asyncio
    async def test_reflect_force(self, db_session, mock_embedding):
        """force=True 跳过条件检查。"""
        mock_llm = MockReflectionLLM(main_response=EMPTY_LLM_RESPONSE)
        await _insert_memories(db_session, mock_embedding, count=1)

        svc = ReflectionService(db_session, mock_embedding, mock_llm)
        result = await svc.reflect("ref_user", force=True)
        assert result["triggered"] is True
        assert result["trigger_type"] == "force"

    @pytest.mark.asyncio
    async def test_reflect_session_ended(self, db_session, mock_embedding):
        """session_ended=True 触发。"""
        mock_llm = MockReflectionLLM(main_response=EMPTY_LLM_RESPONSE)
        await _insert_memories(db_session, mock_embedding, count=1)

        svc = ReflectionService(db_session, mock_embedding, mock_llm)
        result = await svc.reflect("ref_user", session_ended=True)
        assert result["triggered"] is True
        assert result["trigger_type"] == "session_end"

    @pytest.mark.asyncio
    async def test_reflect_creates_trend(self, db_session, mock_embedding):
        """反思生成 trend trait。"""
        mock_llm = MockReflectionLLM(main_response=SIMPLE_TREND_RESPONSE)
        await _insert_memories(db_session, mock_embedding, count=3)

        svc = ReflectionService(db_session, mock_embedding, mock_llm)
        result = await svc.reflect("ref_user", force=True)
        assert result["traits_created"] >= 1

        # 验证 DB 中有 trait
        rows = await db_session.execute(
            text("SELECT COUNT(*) FROM memories WHERE user_id = :uid AND memory_type = 'trait' AND trait_stage = 'trend'"),
            {"uid": "ref_user"},
        )
        assert rows.scalar() >= 1

    @pytest.mark.asyncio
    async def test_reflect_creates_behavior(self, db_session, mock_embedding):
        """反思生成 behavior trait。"""
        mock_llm = MockReflectionLLM(main_response=SIMPLE_BEHAVIOR_RESPONSE)
        await _insert_memories(db_session, mock_embedding, count=3)

        svc = ReflectionService(db_session, mock_embedding, mock_llm)
        result = await svc.reflect("ref_user", force=True)
        assert result["traits_created"] >= 1

        rows = await db_session.execute(
            text("SELECT COUNT(*) FROM memories WHERE user_id = :uid AND memory_type = 'trait' AND trait_subtype = 'behavior'"),
            {"uid": "ref_user"},
        )
        assert rows.scalar() >= 1

    @pytest.mark.asyncio
    async def test_reflect_llm_single_call(self, db_session, mock_embedding):
        """验证步骤 2/4/5/6/7 合并为 1 次 LLM 主调用。"""
        mock_llm = MockReflectionLLM(main_response=EMPTY_LLM_RESPONSE)
        await _insert_memories(db_session, mock_embedding, count=3)

        svc = ReflectionService(db_session, mock_embedding, mock_llm)
        await svc.reflect("ref_user", force=True)
        # 主调用只应该 1 次（无矛盾则无专项反思调用）
        assert mock_llm._call_count == 1

    @pytest.mark.asyncio
    async def test_reflect_no_new_memories_skips_llm(self, db_session, mock_embedding):
        """无新记忆时跳过 LLM 调用，仅执行衰减。"""
        # 设置水位线在未来，确保没有新记忆
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        await _ensure_session(db_session, last_reflected_at=future)

        mock_llm = MockReflectionLLM(main_response=EMPTY_LLM_RESPONSE)
        svc = ReflectionService(db_session, mock_embedding, mock_llm)
        result = await svc.reflect("ref_user", force=True)
        assert mock_llm._call_count == 0
        assert result["memories_scanned"] == 0

    @pytest.mark.asyncio
    async def test_reflect_llm_invalid_json(self, db_session, mock_embedding):
        """LLM 返回无效 JSON 时 fallback 跳过 trait 操作。"""
        mock_llm = MockReflectionLLM(main_response="This is not valid JSON at all")
        await _insert_memories(db_session, mock_embedding, count=3)

        svc = ReflectionService(db_session, mock_embedding, mock_llm)
        result = await svc.reflect("ref_user", force=True)
        # 应该不崩溃，traits_created 应为 0
        assert result["traits_created"] == 0

    @pytest.mark.asyncio
    async def test_reflect_llm_failure(self, db_session, mock_embedding):
        """LLM 调用异常不影响已有数据。"""

        class FailLLM(LLMProvider):
            async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
                raise RuntimeError("LLM down")

        await _insert_memories(db_session, mock_embedding, count=3)
        svc = ReflectionService(db_session, mock_embedding, FailLLM())
        result = await svc.reflect("ref_user", force=True)
        # 应该不崩溃
        assert result["triggered"] is True
        assert result["traits_created"] == 0

    @pytest.mark.asyncio
    async def test_llm_failure_no_watermark_update(self, db_session, mock_embedding):
        """反思流程硬失败（异常逃逸）时 cycle 记录 status=failed，水位线不前进。

        注意：_call_reflection_llm 内部会捕获 LLM 异常并返回 None（软失败），
        此时 reflect() 仍会标记 cycle 为 completed。要测试水位线不前进，
        需要在 _run_reflection_steps 层面触发未捕获的异常。
        """
        from unittest.mock import AsyncMock, patch
        from sqlalchemy import text

        mock_llm = AsyncMock(spec=LLMProvider)

        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        await _ensure_session(db_session, last_reflected_at=old_time)
        await _insert_memories(db_session, mock_embedding, count=3)

        svc = ReflectionService(db_session, mock_embedding, mock_llm)

        # Patch _run_reflection_steps 使其直接抛出异常（模拟硬失败）
        with patch.object(svc, "_run_reflection_steps", side_effect=RuntimeError("DB connection lost")):
            result = await svc.reflect("ref_user", force=True)

        assert result.get("error") is not None

        # 水位线应保持为 old_time（不应有新的 completed cycle）
        row = (await db_session.execute(
            text("SELECT completed_at FROM reflection_cycles "
                 "WHERE user_id = :uid AND status = 'completed' "
                 "ORDER BY completed_at DESC LIMIT 1"),
            {"uid": "ref_user"},
        )).first()
        if row is not None:
            delta = abs((row.completed_at - old_time).total_seconds())
            assert delta < 5  # 水位线应该保持不变

    @pytest.mark.asyncio
    async def test_llm_soft_failure_cycle_still_completed(self, db_session, mock_embedding):
        """LLM 调用异常被 _call_reflection_llm 内部捕获时，cycle 仍为 completed。

        这是设计行为：衰减等非 LLM 步骤仍然执行了，cycle 标记为 completed，
        水位线正常前进。
        """
        from sqlalchemy import text

        class FailLLM(LLMProvider):
            async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
                raise RuntimeError("LLM down")

        await _insert_memories(db_session, mock_embedding, count=3)
        svc = ReflectionService(db_session, mock_embedding, FailLLM())
        result = await svc.reflect("ref_user", force=True)

        assert result["triggered"] is True
        assert result["traits_created"] == 0
        # cycle 应标记为 completed（非 failed）
        row = (await db_session.execute(
            text("SELECT status FROM reflection_cycles WHERE id = :cid"),
            {"cid": result["cycle_id"]},
        )).first()
        assert row is not None
        assert row.status == "completed"

    @pytest.mark.asyncio
    async def test_reflect_cycle_recorded(self, db_session, mock_embedding):
        """reflection_cycles 表正确写入。"""
        mock_llm = MockReflectionLLM(main_response=SIMPLE_TREND_RESPONSE)
        await _insert_memories(db_session, mock_embedding, count=3)

        svc = ReflectionService(db_session, mock_embedding, mock_llm)
        result = await svc.reflect("ref_user", force=True)

        assert result.get("cycle_id") is not None
        rows = await db_session.execute(
            text("SELECT status, memories_scanned, traits_created FROM reflection_cycles WHERE id = :cid"),
            {"cid": result["cycle_id"]},
        )
        cycle = rows.fetchone()
        assert cycle is not None
        assert cycle.status == "completed"

    @pytest.mark.asyncio
    async def test_reflect_updates_watermark(self, db_session, mock_embedding):
        """reflect() 在 reflection_cycles 中创建新的 completed 记录作为水位线。"""
        from sqlalchemy import text

        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        await _ensure_session(db_session, last_reflected_at=old_time)

        mock_llm = MockReflectionLLM(main_response=EMPTY_LLM_RESPONSE)
        await _insert_memories(db_session, mock_embedding, count=1)

        svc = ReflectionService(db_session, mock_embedding, mock_llm)
        await svc.reflect("ref_user", force=True)

        # Verify watermark updated in reflection_cycles
        row = (await db_session.execute(
            text("SELECT completed_at FROM reflection_cycles "
                 "WHERE user_id = :uid AND status = 'completed' "
                 "ORDER BY completed_at DESC LIMIT 1"),
            {"uid": "ref_user"},
        )).first()
        assert row is not None
        delta = abs((row.completed_at - old_time).total_seconds())
        assert delta > 60  # 水位线应已更新

    @pytest.mark.asyncio
    async def test_reflect_returns_expected_format(self, db_session, mock_embedding):
        """reflect() 返回预期格式。"""
        mock_llm = MockReflectionLLM(main_response=EMPTY_LLM_RESPONSE)
        await _insert_memories(db_session, mock_embedding, count=1)

        svc = ReflectionService(db_session, mock_embedding, mock_llm)
        result = await svc.reflect("ref_user", force=True)

        assert "triggered" in result
        assert "trigger_type" in result
        assert "memories_scanned" in result
        assert "traits_created" in result
        assert "traits_updated" in result
        assert "traits_dissolved" in result
        assert "cycle_id" in result


# ====================================================================
# Backward Compatibility
# ====================================================================

class TestDigestCompat:
    """Tests for digest() backward compatibility."""

    @pytest.mark.asyncio
    async def test_digest_backward_compat(self, db_session, mock_embedding, mock_llm):
        """digest() 返回结构不变。"""
        svc = ReflectionService(db_session, mock_embedding, mock_llm)
        result = await svc.digest("compat_user", [
            {"content": "test fact", "memory_type": "fact", "metadata": {}},
        ])
        assert "insights" in result
        assert "emotion_profile" not in result

    @pytest.mark.asyncio
    async def test_digest_empty_memories(self, db_session, mock_embedding, mock_llm):
        """digest() 空输入返回空结果。"""
        svc = ReflectionService(db_session, mock_embedding, mock_llm)
        result = await svc.digest("compat_user", [])
        assert result["insights"] == []
        assert "emotion_profile" not in result


# ====================================================================
# ConversationSession ORM
# ====================================================================

class TestConversationSessionORM:
    """Tests for ConversationSession last_reflected_at field."""

    @pytest.mark.asyncio
    async def test_conversation_session_has_last_reflected_at(self, db_session):
        """ORM 模型包含 last_reflected_at 字段。"""
        from neuromem.models.conversation import ConversationSession
        assert hasattr(ConversationSession, "last_reflected_at")
