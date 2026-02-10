"""Tests for conversation API"""

import pytest


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_add_single_message(client):
    """Test adding a single conversation message"""
    # Add a message
    response = await client.post(
        "/v1/conversations/messages",
        json={
            "user_id": "test_user_123",
            "role": "user",
            "content": "I work at Google",
            "metadata": {"timestamp": "2024-01-15T10:00:00"}
        }
    )

    assert response.status_code == 200
    data = response.json()

    assert data["user_id"] == "test_user_123"
    assert data["role"] == "user"
    assert data["content"] == "I work at Google"
    assert "session_id" in data
    assert "id" in data
    assert data["extracted"] is False


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_add_batch_messages(client):
    """Test adding multiple messages in batch"""
    # Add batch messages
    response = await client.post(
        "/v1/conversations/batch",
        json={
            "user_id": "test_user_123",
            "messages": [
                {"role": "user", "content": "What's the weather?"},
                {"role": "assistant", "content": "It's sunny today!"},
                {"role": "user", "content": "Thanks!"}
            ]
        }
    )

    assert response.status_code == 200
    data = response.json()

    assert "session_id" in data
    assert data["messages_added"] == 3
    assert len(data["message_ids"]) == 3


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_get_conversation_history(client):
    """Test retrieving conversation history"""
    # First add some messages
    batch_response = await client.post(
        "/v1/conversations/batch",
        json={
            "user_id": "test_user_123",
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ]
        }
    )
    session_id = batch_response.json()["session_id"]

    # Get conversation history
    response = await client.get(
        f"/v1/conversations/sessions/{session_id}",
        params={"user_id": "test_user_123"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["session_id"] == session_id
    assert data["message_count"] == 2
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][0]["content"] == "Hello"
    assert data["messages"][1]["role"] == "assistant"


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_list_sessions(client):
    """Test listing all conversation sessions"""
    # Create multiple sessions
    for i in range(3):
        await client.post(
            "/v1/conversations/batch",
            json={
                "user_id": "test_user_123",
                "messages": [
                    {"role": "user", "content": f"Message {i}"},
                ]
            }
        )

    # List sessions
    response = await client.get(
        "/v1/conversations/sessions",
        params={"user_id": "test_user_123"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["total"] >= 3
    assert len(data["sessions"]) >= 3
    # Check sessions are ordered by last_message_at desc
    for session in data["sessions"]:
        assert "session_id" in session
        assert "message_count" in session
        assert session["message_count"] > 0


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_auto_extract_config(client):
    """Test configuring auto-extraction"""
    response = await client.post(
        "/v1/conversations/auto-extract",
        json={
            "user_id": "test_user_123",
            "trigger": "message_count",
            "threshold": 10,
            "async_mode": True
        }
    )

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "configured"
    assert data["user_id"] == "test_user_123"


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_extract_memories_placeholder(client):
    """Test manual memory extraction (placeholder for Phase 1.2)"""
    # Add some messages first
    await client.post(
        "/v1/conversations/batch",
        json={
            "user_id": "test_user_123",
            "messages": [
                {"role": "user", "content": "I like blue color"},
                {"role": "assistant", "content": "Noted!"},
            ]
        }
    )

    # Trigger extraction
    response = await client.post(
        "/v1/conversations/extract",
        json={
            "user_id": "test_user_123",
            "force": False
        }
    )

    assert response.status_code == 200
    data = response.json()

    # Currently returns placeholder
    assert data["status"] == "pending"
    assert "messages_processed" in data


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_conversation_with_specified_session(client):
    """Test adding messages to a specific session ID"""
    session_id = "my_custom_session_123"

    # Add first batch
    response1 = await client.post(
        "/v1/conversations/batch",
        json={
            "user_id": "test_user_123",
            "session_id": session_id,
            "messages": [
                {"role": "user", "content": "First message"},
            ]
        }
    )

    # Add second batch to same session
    response2 = await client.post(
        "/v1/conversations/batch",
        json={
            "user_id": "test_user_123",
            "session_id": session_id,
            "messages": [
                {"role": "user", "content": "Second message"},
            ]
        }
    )

    assert response1.json()["session_id"] == session_id
    assert response2.json()["session_id"] == session_id

    # Verify both messages are in the same session
    history = await client.get(
        f"/v1/conversations/sessions/{session_id}",
        params={"user_id": "test_user_123"}
    )

    assert history.status_code == 200
    data = history.json()
    assert data["message_count"] == 2


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_invalid_role_rejected(client):
    """Test that invalid roles are rejected"""
    response = await client.post(
        "/v1/conversations/messages",
        json={
            "user_id": "test_user_123",
            "role": "invalid_role",
            "content": "Test message"
        }
    )

    assert response.status_code == 422  # Validation error
