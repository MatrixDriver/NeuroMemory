"""Tests for RPIV-1 storage foundation V2: ORM model correctness.

Covers: Memory model fields, auxiliary table CRUD, Embedding alias.
PRD section: 7.3
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError


# ---------------------------------------------------------------------------
# TC-O01: Memory tablename
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_memory_model_tablename():
    """TC-O01: Memory.__tablename__ is 'memories'."""
    from neuromem.models.memory import Memory
    assert Memory.__tablename__ == "memories"


# ---------------------------------------------------------------------------
# TC-O02: Embedding alias
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_embedding_alias_exists():
    """TC-O02: Embedding is importable and is the same class as Memory."""
    from neuromem.models.memory import Memory, Embedding
    assert Embedding is Memory


# ---------------------------------------------------------------------------
# TC-O03: Trait fields roundtrip
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_memory_model_trait_fields_roundtrip(db_session, mock_embedding):
    """TC-O03: All 12 trait fields can be written and read back correctly."""
    from neuromem.models.memory import Memory

    parent_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    vector = await mock_embedding.embed("trait test")

    mem = Memory(
        user_id="trait_test",
        content="trait roundtrip test",
        embedding=vector,
        memory_type="trait",
        metadata_={},
        trait_subtype="preference",
        trait_stage="emerging",
        trait_confidence=0.75,
        trait_context="work",
        trait_parent_id=parent_id,
        trait_reinforcement_count=5,
        trait_contradiction_count=2,
        trait_last_reinforced=now,
        trait_first_observed=now,
        trait_window_start=now,
        trait_window_end=now,
        trait_derived_from="reflection",
    )
    db_session.add(mem)
    await db_session.flush()

    result = await db_session.execute(
        select(Memory).where(Memory.id == mem.id)
    )
    fetched = result.scalar_one()

    assert fetched.trait_subtype == "preference"
    assert fetched.trait_stage == "emerging"
    assert abs(fetched.trait_confidence - 0.75) < 1e-6
    assert fetched.trait_context == "work"
    assert fetched.trait_parent_id == parent_id
    assert fetched.trait_reinforcement_count == 5
    assert fetched.trait_contradiction_count == 2
    assert fetched.trait_last_reinforced is not None
    assert fetched.trait_first_observed is not None
    assert fetched.trait_window_start is not None
    assert fetched.trait_window_end is not None
    assert fetched.trait_derived_from == "reflection"


# ---------------------------------------------------------------------------
# TC-O04: Timeline fields roundtrip
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_memory_model_timeline_fields_roundtrip(db_session, mock_embedding):
    """TC-O04: valid_at/invalid_at/expired_at roundtrip."""
    from neuromem.models.memory import Memory

    now = datetime.now(timezone.utc)
    vector = await mock_embedding.embed("timeline test")

    mem = Memory(
        user_id="timeline_test",
        content="timeline roundtrip",
        embedding=vector,
        memory_type="fact",
        metadata_={},
        valid_at=now,
        invalid_at=now,
        expired_at=now,
    )
    db_session.add(mem)
    await db_session.flush()

    result = await db_session.execute(
        select(Memory).where(Memory.id == mem.id)
    )
    fetched = result.scalar_one()

    assert fetched.valid_at is not None
    assert fetched.invalid_at is not None
    assert fetched.expired_at is not None


# ---------------------------------------------------------------------------
# TC-O05: content_hash roundtrip
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_memory_model_content_hash_roundtrip(db_session, mock_embedding):
    """TC-O05: content_hash stores 32-char MD5 correctly."""
    from neuromem.models.memory import Memory

    vector = await mock_embedding.embed("hash test")
    test_hash = "d41d8cd98f00b204e9800998ecf8427e"

    mem = Memory(
        user_id="hash_test",
        content="hash roundtrip",
        embedding=vector,
        memory_type="fact",
        metadata_={},
        content_hash=test_hash,
    )
    db_session.add(mem)
    await db_session.flush()

    result = await db_session.execute(
        select(Memory).where(Memory.id == mem.id)
    )
    fetched = result.scalar_one()
    assert fetched.content_hash == test_hash


# ---------------------------------------------------------------------------
# TC-O06: Entity fields roundtrip
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_memory_model_entity_fields_roundtrip(db_session, mock_embedding):
    """TC-O06: subject_entity_id/object_entity_id UUID roundtrip."""
    from neuromem.models.memory import Memory

    subj_id = uuid.uuid4()
    obj_id = uuid.uuid4()
    vector = await mock_embedding.embed("entity test")

    mem = Memory(
        user_id="entity_test",
        content="entity roundtrip",
        embedding=vector,
        memory_type="fact",
        metadata_={},
        subject_entity_id=subj_id,
        object_entity_id=obj_id,
    )
    db_session.add(mem)
    await db_session.flush()

    result = await db_session.execute(
        select(Memory).where(Memory.id == mem.id)
    )
    fetched = result.scalar_one()
    assert fetched.subject_entity_id == subj_id
    assert fetched.object_entity_id == obj_id


# ---------------------------------------------------------------------------
# TC-O07: source_episode_ids array
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_memory_model_source_episode_ids(db_session, mock_embedding):
    """TC-O07: source_episode_ids stores UUID array correctly."""
    from neuromem.models.memory import Memory

    ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    vector = await mock_embedding.embed("episode ids test")

    mem = Memory(
        user_id="episode_test",
        content="source episode ids test",
        embedding=vector,
        memory_type="fact",
        metadata_={},
        source_episode_ids=ids,
    )
    db_session.add(mem)
    await db_session.flush()

    result = await db_session.execute(
        select(Memory).where(Memory.id == mem.id)
    )
    fetched = result.scalar_one()
    assert fetched.source_episode_ids is not None
    assert len(fetched.source_episode_ids) == 3


# ---------------------------------------------------------------------------
# TC-O08: TraitEvidence CRUD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trait_evidence_crud(db_session):
    """TC-O08: TraitEvidence create/read with CHECK constraints."""
    from neuromem.models.trait_evidence import TraitEvidence

    trait_id = uuid.uuid4()
    memory_id = uuid.uuid4()

    evidence = TraitEvidence(
        trait_id=trait_id,
        memory_id=memory_id,
        evidence_type="supporting",
        quality="A",
    )
    db_session.add(evidence)
    await db_session.flush()

    result = await db_session.execute(
        select(TraitEvidence).where(TraitEvidence.id == evidence.id)
    )
    fetched = result.scalar_one()
    assert fetched.trait_id == trait_id
    assert fetched.memory_id == memory_id
    assert fetched.evidence_type == "supporting"
    assert fetched.quality == "A"
    assert fetched.created_at is not None


@pytest.mark.asyncio
async def test_trait_evidence_check_constraints(db_session):
    """TC-O08 (constraints): Invalid evidence_type or quality triggers error."""
    from neuromem.models.trait_evidence import TraitEvidence

    # Invalid evidence_type
    bad_evidence = TraitEvidence(
        trait_id=uuid.uuid4(),
        memory_id=uuid.uuid4(),
        evidence_type="invalid",
        quality="A",
    )
    db_session.add(bad_evidence)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()

    # Invalid quality
    bad_quality = TraitEvidence(
        trait_id=uuid.uuid4(),
        memory_id=uuid.uuid4(),
        evidence_type="supporting",
        quality="E",
    )
    db_session.add(bad_quality)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


# ---------------------------------------------------------------------------
# TC-O09: MemoryHistory CRUD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_memory_history_crud(db_session):
    """TC-O09: MemoryHistory create/read for all event types."""
    from neuromem.models.memory_history import MemoryHistory

    events = ["ADD", "UPDATE", "DELETE", "SUPERSEDE", "STAGE_CHANGE"]

    for event in events:
        history = MemoryHistory(
            memory_id=uuid.uuid4(),
            memory_type="fact",
            event=event,
            old_content=None if event == "ADD" else "old",
            new_content="new content",
            actor="system",
        )
        db_session.add(history)

    await db_session.flush()

    result = await db_session.execute(select(MemoryHistory))
    rows = result.scalars().all()
    assert len(rows) == 5

    event_types = {r.event for r in rows}
    assert event_types == set(events)
    assert all(r.created_at is not None for r in rows)


# ---------------------------------------------------------------------------
# TC-O10: ReflectionCycle CRUD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reflection_cycle_crud(db_session):
    """TC-O10: ReflectionCycle create/read with status update."""
    from neuromem.models.reflection_cycle import ReflectionCycle

    cycle = ReflectionCycle(
        user_id="reflection_test",
        trigger_type="importance_accumulated",
        trigger_value=32.5,
    )
    db_session.add(cycle)
    await db_session.flush()

    result = await db_session.execute(
        select(ReflectionCycle).where(ReflectionCycle.id == cycle.id)
    )
    fetched = result.scalar_one()

    assert fetched.trigger_type == "importance_accumulated"
    assert abs(fetched.trigger_value - 32.5) < 0.01
    assert fetched.memories_scanned == 0
    assert fetched.traits_created == 0
    assert fetched.traits_updated == 0
    assert fetched.traits_dissolved == 0
    assert fetched.status == "running"
    assert fetched.started_at is not None
    assert fetched.completed_at is None

    # Update status
    fetched.status = "completed"
    fetched.completed_at = datetime.now(timezone.utc)
    fetched.memories_scanned = 42
    fetched.traits_created = 3
    await db_session.flush()

    result = await db_session.execute(
        select(ReflectionCycle).where(ReflectionCycle.id == cycle.id)
    )
    updated = result.scalar_one()
    assert updated.status == "completed"
    assert updated.completed_at is not None
    assert updated.memories_scanned == 42
    assert updated.traits_created == 3


# ---------------------------------------------------------------------------
# TC-O11: MemorySource CRUD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_memory_source_crud(db_session):
    """TC-O11: MemorySource create/read with composite PK."""
    from neuromem.models.memory_source import MemorySource

    mem_id = uuid.uuid4()
    sess_id = uuid.uuid4()
    conv_id = uuid.uuid4()

    source = MemorySource(
        memory_id=mem_id,
        session_id=sess_id,
        conversation_id=conv_id,
    )
    db_session.add(source)
    await db_session.flush()

    result = await db_session.execute(
        select(MemorySource).where(
            MemorySource.memory_id == mem_id,
            MemorySource.session_id == sess_id,
        )
    )
    fetched = result.scalar_one()
    assert fetched.memory_id == mem_id
    assert fetched.session_id == sess_id
    assert fetched.conversation_id == conv_id
    assert fetched.created_at is not None


# ---------------------------------------------------------------------------
# TC-O12: MemorySource composite PK uniqueness
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_memory_source_composite_pk_unique(db_session):
    """TC-O12: Duplicate (memory_id, session_id) triggers IntegrityError."""
    from neuromem.models.memory_source import MemorySource

    mem_id = uuid.uuid4()
    sess_id = uuid.uuid4()

    db_session.add(MemorySource(memory_id=mem_id, session_id=sess_id))
    await db_session.flush()

    db_session.add(MemorySource(memory_id=mem_id, session_id=sess_id))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


# ---------------------------------------------------------------------------
# TC-O13: All auxiliary tables created by create_all
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_auxiliary_tables_created(db_session):
    """TC-O13: trait_evidence, memory_history, reflection_cycles, memory_sources all exist."""
    tables = ["trait_evidence", "memory_history", "reflection_cycles", "memory_sources"]
    for table_name in tables:
        result = await db_session.execute(
            text("SELECT to_regclass(:t) IS NOT NULL"),
            {"t": table_name},
        )
        assert result.scalar(), f"Table '{table_name}' does not exist"
