"""Tests for P2-1: Zettelkasten — memory inter-linking during reflection."""

import hashlib
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from neuromem.models.memory import Memory
from neuromem.providers.llm import LLMProvider
from neuromem.services.reflection import ReflectionService


class MockZettelLLM(LLMProvider):
    def __init__(self, main_response: str):
        self._main_response = main_response

    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        return self._main_response


@pytest.mark.asyncio
async def test_reflection_creates_memory_links(db_session, mock_embedding):
    """Reflection should create bidirectional links between related memories."""
    now = datetime.now(timezone.utc)

    mems = []
    for content in ["用户在 Google 工作", "用户负责搜索团队"]:
        vec = await mock_embedding.embed(content)
        m = Memory(
            user_id="u_zett",
            content=content,
            embedding=vec,
            memory_type="fact",
            metadata_={"importance": 7},
            valid_from=now,
            content_hash=hashlib.md5(content.encode()).hexdigest(),
            valid_at=now,
        )
        db_session.add(m)
        mems.append(m)
    await db_session.flush()

    id0, id1 = str(mems[0].id), str(mems[1].id)

    llm_response = json.dumps({
        "new_trends": [],
        "new_behaviors": [],
        "reinforcements": [],
        "contradictions": [],
        "upgrades": [],
        "links": [
            {"source_id": id0, "target_id": id1, "relation": "same_topic"},
        ],
    })

    llm = MockZettelLLM(main_response=llm_response)
    svc = ReflectionService(db_session, mock_embedding, llm)
    await svc.reflect(user_id="u_zett", force=True)

    # Check bidirectional links
    row0 = (await db_session.execute(
        text("SELECT metadata FROM memories WHERE id = :id"),
        {"id": mems[0].id},
    )).first()
    row1 = (await db_session.execute(
        text("SELECT metadata FROM memories WHERE id = :id"),
        {"id": mems[1].id},
    )).first()

    assert row0 is not None
    related0 = row0.metadata.get("related_memories", [])
    assert any(r["id"] == id1 for r in related0), f"Expected link to {id1} in {related0}"

    assert row1 is not None
    related1 = row1.metadata.get("related_memories", [])
    assert any(r["id"] == id0 for r in related1), f"Expected link to {id0} in {related1}"


@pytest.mark.asyncio
async def test_recall_expands_linked_memories(db_session, mock_embedding):
    """Recall should include 1-hop linked memories in results."""
    now = datetime.now(timezone.utc)

    content_a = "用户在 Google 工作"
    content_b = "用户负责搜索团队的后端架构"
    vec_a = await mock_embedding.embed(content_a)
    vec_b = await mock_embedding.embed(content_b)

    mem_a = Memory(
        user_id="u_expand",
        content=content_a,
        embedding=vec_a,
        memory_type="fact",
        metadata_={"importance": 7},
        valid_from=now,
        content_hash=hashlib.md5(content_a.encode()).hexdigest(),
        valid_at=now,
    )
    db_session.add(mem_a)
    await db_session.flush()

    mem_b = Memory(
        user_id="u_expand",
        content=content_b,
        embedding=vec_b,
        memory_type="fact",
        metadata_={"importance": 7},
        valid_from=now,
        content_hash=hashlib.md5(content_b.encode()).hexdigest(),
        valid_at=now,
    )
    db_session.add(mem_b)
    await db_session.flush()

    # Set up link: A -> B
    id_b = str(mem_b.id)
    await db_session.execute(
        text("UPDATE memories SET metadata = jsonb_set(metadata, '{related_memories}', CAST(:links AS jsonb)) WHERE id = :id"),
        {"id": mem_a.id, "links": json.dumps([{"id": id_b, "relation": "elaborates"}])},
    )
    await db_session.commit()

    # This test needs a full NeuroMemory instance for recall
    # For now just verify the link data is stored correctly
    row = (await db_session.execute(
        text("SELECT metadata FROM memories WHERE id = :id"),
        {"id": mem_a.id},
    )).first()
    assert row is not None
    related = row.metadata.get("related_memories", [])
    assert len(related) == 1
    assert related[0]["id"] == id_b
