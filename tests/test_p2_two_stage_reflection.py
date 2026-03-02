"""Tests for P2-2: Two-Stage Reflection."""

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from neuromem.models.memory import Memory
from neuromem.models.reflection_cycle import ReflectionCycle
from neuromem.providers.llm import LLMProvider
from neuromem.services.reflection import ReflectionService


class MockTwoStageLLM(LLMProvider):
    """Mock LLM that tracks call count for two-stage verification."""

    def __init__(self, responses: list[str]):
        self._responses = responses
        self._call_count = 0
        self.call_history: list[list[dict]] = []

    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        self._call_count += 1
        self.call_history.append(messages)
        idx = min(self._call_count - 1, len(self._responses) - 1)
        return self._responses[idx]


@pytest.mark.asyncio
async def test_two_stage_reflection_on_importance_trigger(db_session, mock_embedding):
    """importance_accumulated trigger should use two-stage (2 LLM calls)."""
    now = datetime.now(timezone.utc)

    # Create a prior completed reflection cycle so trigger is importance_accumulated, not first_time
    prior_cycle = ReflectionCycle(
        user_id="u_2stage",
        trigger_type="force",
        status="completed",
        completed_at=now - timedelta(hours=2),
    )
    db_session.add(prior_cycle)
    await db_session.flush()

    # Create enough high-importance memories to trigger importance_accumulated (>=30)
    for i in range(6):
        content = f"用户讨论了重要的技术决策 {i}"
        vec = await mock_embedding.embed(content)
        m = Memory(
            user_id="u_2stage",
            content=content,
            embedding=vec,
            memory_type="fact",
            metadata_={"importance": 8},  # 6 * 8 = 48 >= 30
            valid_from=now,
            content_hash=hashlib.md5(content.encode()).hexdigest(),
            valid_at=now,
        )
        db_session.add(m)
    await db_session.flush()

    stage1 = json.dumps({"questions": ["用户的技术偏好?", "工作重心?"]})
    stage2 = json.dumps({
        "new_trends": [{"content": "频繁讨论技术决策", "evidence_ids": [], "window_days": 30, "context": "work"}],
        "new_behaviors": [], "reinforcements": [], "contradictions": [], "upgrades": [], "links": [],
    })

    llm = MockTwoStageLLM(responses=[stage1, stage2])
    svc = ReflectionService(db_session, mock_embedding, llm)
    result = await svc.reflect(user_id="u_2stage", force=False)

    assert result["triggered"] is True
    assert result["trigger_type"] == "importance_accumulated"
    assert llm._call_count == 2  # Two-stage: questions + analysis
    assert result["traits_created"] >= 1


@pytest.mark.asyncio
async def test_single_stage_for_force_trigger(db_session, mock_embedding):
    """force=True should use single-stage (1 LLM call)."""
    now = datetime.now(timezone.utc)

    content = "用户喜欢咖啡"
    vec = await mock_embedding.embed(content)
    m = Memory(
        user_id="u_1stage",
        content=content,
        embedding=vec,
        memory_type="fact",
        metadata_={"importance": 3},
        valid_from=now,
        content_hash=hashlib.md5(content.encode()).hexdigest(),
        valid_at=now,
    )
    db_session.add(m)
    await db_session.flush()

    response = json.dumps({
        "new_trends": [], "new_behaviors": [],
        "reinforcements": [], "contradictions": [], "upgrades": [], "links": [],
    })

    llm = MockTwoStageLLM(responses=[response])
    svc = ReflectionService(db_session, mock_embedding, llm)
    result = await svc.reflect(user_id="u_1stage", force=True)

    assert result["triggered"] is True
    assert llm._call_count == 1  # Single-stage
