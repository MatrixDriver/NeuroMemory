"""Tests for MemoryService CRUD operations."""

from __future__ import annotations

import pytest

from neuromem.services.memory import MemoryService
from neuromem.services.search import SearchService


@pytest.mark.asyncio
async def test_list_all_memories(db_session, mock_embedding):
    """Test listing all memories with pagination."""
    user_id = "test_user_list"

    # Add some test memories
    search_service = SearchService(db_session, mock_embedding)
    for i in range(5):
        await search_service.add_memory(
            user_id=user_id,
            content=f"Test memory {i}",
            memory_type="fact" if i % 2 == 0 else "episodic",
        )
    await db_session.commit()

    # Test list all
    memory_service = MemoryService(db_session, mock_embedding)
    total, memories = await memory_service.list_all_memories(user_id, limit=10)

    assert total == 5
    assert len(memories) == 5
    assert all(m.user_id == user_id for m in memories)

    # Test filtering by type
    total, memories = await memory_service.list_all_memories(
        user_id, memory_type="fact", limit=10
    )

    assert total == 3  # 0, 2, 4
    assert len(memories) == 3
    assert all(m.memory_type == "fact" for m in memories)

    # Test pagination
    total, page1 = await memory_service.list_all_memories(user_id, limit=2, offset=0)
    assert total == 5
    assert len(page1) == 2

    total, page2 = await memory_service.list_all_memories(user_id, limit=2, offset=2)
    assert total == 5
    assert len(page2) == 2


@pytest.mark.asyncio
async def test_get_memory_by_id(db_session, mock_embedding):
    """Test getting a single memory by ID."""
    user_id = "test_user_get"

    # Add a test memory
    search_service = SearchService(db_session, mock_embedding)
    memory = await search_service.add_memory(
        user_id=user_id,
        content="Test memory for get",
        memory_type="fact",
    )
    await db_session.commit()
    memory_id = memory.id

    # Get by ID
    memory_service = MemoryService(db_session, mock_embedding)
    fetched = await memory_service.get_memory_by_id(memory_id, user_id)

    assert fetched is not None
    assert fetched.id == memory_id
    assert fetched.content == "Test memory for get"
    assert fetched.user_id == user_id

    # Test with wrong user_id
    fetched = await memory_service.get_memory_by_id(memory_id, "wrong_user")
    assert fetched is None


@pytest.mark.asyncio
async def test_update_memory(db_session, mock_embedding):
    """Test updating a memory."""
    user_id = "test_user_update"

    # Add a test memory
    search_service = SearchService(db_session, mock_embedding)
    memory = await search_service.add_memory(
        user_id=user_id,
        content="Original content",
        memory_type="fact",
        metadata={"source": "test"},
    )
    await db_session.commit()
    memory_id = memory.id
    original_embedding = memory.embedding.copy()

    # Update content (should regenerate embedding)
    memory_service = MemoryService(db_session, mock_embedding)
    updated = await memory_service.update_memory(
        memory_id=memory_id,
        user_id=user_id,
        content="Updated content",
    )
    await db_session.commit()

    assert updated is not None
    assert updated.content == "Updated content"
    # Embedding should change when content changes
    assert updated.embedding != original_embedding

    # Update type and metadata
    updated = await memory_service.update_memory(
        memory_id=memory_id,
        user_id=user_id,
        memory_type="episodic",
        metadata={"source": "updated"},
    )
    await db_session.commit()

    assert updated is not None
    assert updated.memory_type == "episodic"
    assert updated.metadata_["source"] == "updated"

    # Test updating non-existent memory
    updated = await memory_service.update_memory(
        memory_id="00000000-0000-0000-0000-000000000000",
        user_id=user_id,
        content="Should fail",
    )

    assert updated is None


@pytest.mark.asyncio
async def test_delete_memory(db_session, mock_embedding):
    """Test deleting a memory."""
    user_id = "test_user_delete"

    # Add a test memory
    search_service = SearchService(db_session, mock_embedding)
    memory = await search_service.add_memory(
        user_id=user_id,
        content="Memory to delete",
        memory_type="fact",
    )
    await db_session.commit()
    memory_id = memory.id

    # Verify it exists
    memory_service = MemoryService(db_session, mock_embedding)
    fetched = await memory_service.get_memory_by_id(memory_id, user_id)
    assert fetched is not None

    # Delete it
    deleted = await memory_service.delete_memory(memory_id, user_id)
    await db_session.commit()

    assert deleted is True

    # Verify it's gone
    fetched = await memory_service.get_memory_by_id(memory_id, user_id)
    assert fetched is None

    # Test deleting non-existent memory
    deleted = await memory_service.delete_memory(
        "00000000-0000-0000-0000-000000000000", user_id
    )

    assert deleted is False
