"""Tests for conversation service."""

import pytest

from neuromem.services.conversation import ConversationService


@pytest.mark.asyncio
async def test_add_single_message(db_session):
    svc = ConversationService(db_session)
    msg = await svc.ingest(
        user_id="test_user",
        role="user",
        content="I work at Google",
        metadata={"timestamp": "2024-01-15T10:00:00"},
    )

    assert msg.user_id == "test_user"
    assert msg.role == "user"
    assert msg.content == "I work at Google"
    assert msg.session_id is not None
    assert msg.extracted is False


@pytest.mark.asyncio
async def test_add_batch_messages(db_session):
    svc = ConversationService(db_session)
    session_id, message_ids = await svc.add_messages_batch(
        user_id="test_user",
        messages=[
            {"role": "user", "content": "What's the weather?"},
            {"role": "assistant", "content": "It's sunny today!"},
            {"role": "user", "content": "Thanks!"},
        ],
    )

    assert session_id is not None
    assert len(message_ids) == 3


@pytest.mark.asyncio
async def test_get_conversation_history(db_session):
    svc = ConversationService(db_session)
    session_id, _ = await svc.add_messages_batch(
        user_id="test_user",
        messages=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ],
    )

    messages = await svc.get_session_messages(
        user_id="test_user", session_id=session_id
    )
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[0].content == "Hello"
    assert messages[1].role == "assistant"


@pytest.mark.asyncio
async def test_list_sessions(db_session):
    svc = ConversationService(db_session)
    for i in range(3):
        await svc.add_messages_batch(
            user_id="test_user",
            messages=[{"role": "user", "content": f"Message {i}"}],
        )

    total, sessions = await svc.list_sessions(user_id="test_user")
    assert total >= 3
    assert len(sessions) >= 3
    for session in sessions:
        assert session.message_count > 0


@pytest.mark.asyncio
async def test_conversation_with_specified_session(db_session):
    svc = ConversationService(db_session)
    session_id = "my_custom_session_123"

    await svc.add_messages_batch(
        user_id="test_user",
        messages=[{"role": "user", "content": "First message"}],
        session_id=session_id,
    )
    await svc.add_messages_batch(
        user_id="test_user",
        messages=[{"role": "user", "content": "Second message"}],
        session_id=session_id,
    )

    messages = await svc.get_session_messages(
        user_id="test_user", session_id=session_id
    )
    assert len(messages) == 2


@pytest.mark.asyncio
async def test_unextracted_messages(db_session):
    svc = ConversationService(db_session)
    _, msg_ids = await svc.add_messages_batch(
        user_id="test_user",
        messages=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ],
    )

    unextracted = await svc.get_unextracted_messages(user_id="test_user")
    assert len(unextracted) >= 2

    await svc.mark_messages_extracted(msg_ids)

    unextracted_after = await svc.get_unextracted_messages(user_id="test_user")
    assert len(unextracted_after) == 0


@pytest.mark.asyncio
async def test_conversations_via_facade(nm):
    """Test conversations through the NeuroMemory facade."""
    msg = await nm.conversations.ingest(
        user_id="facade_user",
        role="user",
        content="Test message via facade",
    )
    assert msg.content == "Test message via facade"

    session_id, ids = await nm.conversations.add_messages_batch(
        user_id="facade_user",
        messages=[
            {"role": "user", "content": "Batch 1"},
            {"role": "assistant", "content": "Batch 2"},
        ],
    )
    assert len(ids) == 2
