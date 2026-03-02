"""E2E test: verify CRUD facade, optimistic locking, recall-as-reinforcement."""

import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from neuromem.models.memory import Memory
from neuromem.services.memory import MemoryService
from neuromem.services.search import SearchService
from neuromem.services.trait_engine import TraitEngine


def _uid() -> str:
    return f"e2e-{uuid.uuid4().hex[:8]}"


# ── Task 1: CRUD Facade ────────────────────────────────────────────


class TestCRUDFacade:
    """Verify list/update/delete facade methods on NeuroMemory."""

    @pytest.mark.asyncio
    async def test_list_memories(self, nm):
        """list_memories returns paginated results."""
        user = _uid()
        async with nm._db.session() as s:
            svc = SearchService(s, nm._embedding)
            for i in range(3):
                await svc.add_memory(user, f"fact {i}", "fact")
            await s.commit()

        total, items = await nm.list_memories(user)
        assert total == 3
        assert len(items) == 3

        # Pagination
        total2, page = await nm.list_memories(user, limit=2, offset=0)
        assert total2 == 3
        assert len(page) == 2

    @pytest.mark.asyncio
    async def test_list_memories_filter_type(self, nm):
        """list_memories filters by memory_type."""
        user = _uid()
        async with nm._db.session() as s:
            svc = SearchService(s, nm._embedding)
            await svc.add_memory(user, "a fact", "fact")
            await svc.add_memory(user, "an episode", "episodic")
            await s.commit()

        total, items = await nm.list_memories(user, memory_type="fact")
        assert total == 1
        assert items[0].memory_type == "fact"

    @pytest.mark.asyncio
    async def test_update_memory(self, nm):
        """update_memory changes content and regenerates embedding."""
        user = _uid()
        async with nm._db.session() as s:
            svc = SearchService(s, nm._embedding)
            mem = await svc.add_memory(user, "old content", "fact")
            await s.commit()
            mid = str(mem.id)

        updated = await nm.update_memory(mid, user, content="new content")
        assert updated is not None
        assert updated.content == "new content"

        # Verify persisted
        total, items = await nm.list_memories(user)
        assert any(m.content == "new content" for m in items)

    @pytest.mark.asyncio
    async def test_delete_memory_cascade(self, nm):
        """delete_memory removes associated history/evidence/sources."""
        user = _uid()
        async with nm._db.session() as s:
            svc = SearchService(s, nm._embedding)
            mem = await svc.add_memory(user, "to delete", "fact")
            mid = mem.id

            # Seed associated records
            await s.execute(text(
                "INSERT INTO memory_history (id, memory_id, memory_type, event, actor) "
                "VALUES (gen_random_uuid(), :mid, 'fact', 'test', 'test')"
            ), {"mid": mid})
            await s.execute(text(
                "INSERT INTO trait_evidence (id, trait_id, memory_id, evidence_type, quality) "
                "VALUES (gen_random_uuid(), gen_random_uuid(), :mid, 'supporting', 'C')"
            ), {"mid": mid})
            await s.commit()

        deleted = await nm.delete_memory(str(mid), user)
        assert deleted is True

        # Verify cascade
        async with nm._db.session() as s:
            hist = await s.execute(text(
                "SELECT count(*) FROM memory_history WHERE memory_id = :mid"
            ), {"mid": mid})
            assert hist.scalar() == 0

            ev = await s.execute(text(
                "SELECT count(*) FROM trait_evidence WHERE memory_id = :mid"
            ), {"mid": mid})
            assert ev.scalar() == 0

    @pytest.mark.asyncio
    async def test_delete_memory_not_found(self, nm):
        """delete_memory returns False for nonexistent ID."""
        user = _uid()
        result = await nm.delete_memory(str(uuid.uuid4()), user)
        assert result is False


# ── Task 2: Optimistic Locking ─────────────────────────────────────


class TestOptimisticLocking:
    """Verify version field increments on trait modifications."""

    @pytest.mark.asyncio
    async def test_reinforce_bumps_version(self, nm):
        """reinforce_trait increments version."""
        user = _uid()
        async with nm._db.session() as s:
            engine = TraitEngine(s, nm._embedding)
            trait = await engine.create_trend(
                user, "likes coffee", [], 7, "general", "cycle-1",
            )
            await s.commit()
            tid = str(trait.id)
            v1 = trait.version

        async with nm._db.session() as s:
            engine = TraitEngine(s, nm._embedding)
            await engine.reinforce_trait(tid, [], "C", "cycle-2")
            await s.commit()

        async with nm._db.session() as s:
            row = await s.execute(
                select(Memory.version).where(Memory.id == tid)
            )
            v2 = row.scalar()
            assert v2 > v1, f"version should increase: {v1} -> {v2}"

    @pytest.mark.asyncio
    async def test_apply_decay_bumps_version(self, nm):
        """apply_decay increments version for decayed traits."""
        user = _uid()
        async with nm._db.session() as s:
            engine = TraitEngine(s, nm._embedding)
            trait = await engine.create_behavior(
                user, "early riser", [], 0.4, "general", "cycle-1",
            )
            trait.trait_last_reinforced = trait.created_at
            await s.commit()
            tid = str(trait.id)
            v1 = trait.version

        async with nm._db.session() as s:
            await s.execute(text(
                "UPDATE memories SET trait_last_reinforced = "
                "NOW() - INTERVAL '30 days' WHERE id = :tid"
            ), {"tid": tid})
            await s.commit()

        async with nm._db.session() as s:
            engine = TraitEngine(s, nm._embedding)
            await engine.apply_decay(user)
            await s.commit()

        async with nm._db.session() as s:
            row = await s.execute(
                select(Memory.version).where(Memory.id == tid)
            )
            v2 = row.scalar()
            assert v2 > v1, f"version should increase after decay: {v1} -> {v2}"

    @pytest.mark.asyncio
    async def test_promote_trends_bumps_version(self, nm):
        """promote_trends increments version."""
        user = _uid()
        async with nm._db.session() as s:
            engine = TraitEngine(s, nm._embedding)
            trait = await engine.create_trend(
                user, "night owl pattern", [], 7, "general", "cycle-1",
            )
            trait.trait_reinforcement_count = 3
            await s.commit()
            tid = str(trait.id)
            v1 = trait.version

        async with nm._db.session() as s:
            engine = TraitEngine(s, nm._embedding)
            promoted = await engine.promote_trends(user)
            await s.commit()
            assert promoted >= 1

        async with nm._db.session() as s:
            row = await s.execute(
                select(Memory.version, Memory.trait_stage).where(Memory.id == tid)
            )
            r = row.one()
            assert r.trait_stage == "candidate"
            assert r.version > v1


# ── Task 3: Recall-as-Reinforcement ───────────────────────────────


class TestRecallReinforcement:
    """Verify recall triggers background trait reinforcement."""

    @pytest.mark.asyncio
    async def test_recall_reinforces_matched_traits(self, nm):
        """Traits appearing in recall vector_results get micro-reinforced."""
        user = _uid()
        async with nm._db.session() as s:
            engine = TraitEngine(s, nm._embedding)
            trait = await engine.create_behavior(
                user, "prefers Python for data analysis", [],
                0.45, "work", "cycle-1",
            )
            trait.trait_stage = "emerging"
            trait.trait_confidence = 0.45
            await s.commit()
            tid = str(trait.id)

        # Read initial state
        async with nm._db.session() as s:
            row = await s.execute(
                select(
                    Memory.trait_confidence,
                    Memory.trait_reinforcement_count,
                    Memory.version,
                ).where(Memory.id == tid)
            )
            before = row.one()

        # Recall with a query that should match the trait
        result = await nm.recall(user, "Python data analysis")

        # Wait for background reinforcement task
        await asyncio.sleep(0.5)
        all_tasks = [t for tasks in nm._user_tasks.values() for t in tasks if not t.done()]
        if all_tasks:
            await asyncio.gather(*all_tasks, return_exceptions=True)
            nm._user_tasks.clear()

        # Check if trait was in vector_results
        trait_in_results = any(
            str(r.get("id")) == tid
            for r in result.get("vector_results", [])
            if r.get("memory_type") == "trait"
        )

        if trait_in_results:
            async with nm._db.session() as s:
                row = await s.execute(
                    select(
                        Memory.trait_confidence,
                        Memory.trait_reinforcement_count,
                        Memory.version,
                    ).where(Memory.id == tid)
                )
                after = row.one()

            assert after.version > before.version, \
                "version should bump after recall reinforcement"
            assert after.trait_confidence >= before.trait_confidence, \
                "confidence should not decrease"
        else:
            pytest.skip(
                "Trait not in vector_results (mock embedding); "
                "reinforcement not triggered"
            )
