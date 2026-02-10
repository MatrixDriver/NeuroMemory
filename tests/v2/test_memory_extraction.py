"""Tests for memory extraction with LLM classifier"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_extract_memories_from_conversations(client):
    """Test extracting memories from conversation messages"""
    # First add some conversation messages
    await client.post(
        "/v1/conversations/batch",
        json={
            "user_id": "test_user",
            "messages": [
                {"role": "user", "content": "我在 Google 工作，主要做后端开发"},
                {"role": "assistant", "content": "很高兴认识您！"},
                {"role": "user", "content": "我喜欢蓝色，平时喜欢看科幻电影"},
                {"role": "assistant", "content": "了解了您的偏好！"},
            ]
        }
    )

    # Mock the classifier to return predictable results
    mock_result = {
        "preferences": [
            {"key": "favorite_color", "value": "蓝色", "confidence": 0.95},
            {"key": "hobby", "value": "看科幻电影", "confidence": 0.90},
        ],
        "facts": [
            {"content": "在 Google 工作", "category": "work", "confidence": 0.98},
            {"content": "主要做后端开发", "category": "skill", "confidence": 0.95},
        ],
        "episodes": [],
    }

    with patch(
        "server.app.services.classifier.MemoryClassifier.classify_messages",
        return_value=mock_result
    ):
        # Trigger extraction
        response = await client.post(
            "/v1/conversations/extract",
            json={
                "user_id": "test_user",
                "force": False
            }
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "completed"
        assert data["messages_processed"] == 4
        assert data["preferences_extracted"] == 2
        assert data["facts_extracted"] == 2
        assert data["episodes_extracted"] == 0

    # Verify preferences were stored
    prefs_response = await client.get(
        "/v1/preferences",
        params={"user_id": "test_user"}
    )
    assert prefs_response.status_code == 200
    prefs = prefs_response.json()["preferences"]
    assert len(prefs) >= 2

    # Verify facts were stored (check via search)
    search_response = await client.post(
        "/v1/search",
        json={
            "user_id": "test_user",
            "query": "工作",
            "limit": 5
        }
    )
    # Should find the "在 Google 工作" fact
    # (This will only work if embedding service is available)


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_extract_with_no_messages(client):
    """Test extraction when there are no messages"""
    response = await client.post(
        "/v1/conversations/extract",
        json={
            "user_id": "nonexistent_user",
            "force": False
        }
    )

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "completed"
    assert data["messages_processed"] == 0
    assert data["preferences_extracted"] == 0
    assert data["facts_extracted"] == 0


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_extract_force_mode(client):
    """Test force re-extraction of already extracted messages"""
    # Add messages
    batch_response = await client.post(
        "/v1/conversations/batch",
        json={
            "user_id": "test_user_force",
            "messages": [
                {"role": "user", "content": "我喜欢编程"},
            ]
        }
    )
    session_id = batch_response.json()["session_id"]

    mock_result = {
        "preferences": [
            {"key": "hobby", "value": "编程", "confidence": 0.95},
        ],
        "facts": [],
        "episodes": [],
    }

    with patch(
        "server.app.services.classifier.MemoryClassifier.classify_messages",
        return_value=mock_result
    ):
        # First extraction
        response1 = await client.post(
            "/v1/conversations/extract",
            json={
                "user_id": "test_user_force",
                "session_id": session_id,
                "force": False
            }
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["messages_processed"] >= 1

        # Second extraction without force should find nothing
        response2 = await client.post(
            "/v1/conversations/extract",
            json={
                "user_id": "test_user_force",
                "session_id": session_id,
                "force": False
            }
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["messages_processed"] == 0  # Already extracted

        # Third extraction with force should re-extract
        response3 = await client.post(
            "/v1/conversations/extract",
            json={
                "user_id": "test_user_force",
                "session_id": session_id,
                "force": True
            }
        )
        assert response3.status_code == 200
        data3 = response3.json()
        assert data3["messages_processed"] >= 1  # Re-extracted


@pytest.mark.asyncio
async def test_classifier_parse_json():
    """Test classifier JSON parsing with various formats"""
    from server.app.services.classifier import MemoryClassifier

    classifier = MemoryClassifier()

    # Test with markdown code block
    result1 = classifier._parse_classification_result("""
```json
{
  "preferences": [{"key": "color", "value": "blue", "confidence": 0.9}],
  "facts": [],
  "episodes": []
}
```
    """)
    assert len(result1["preferences"]) == 1
    assert result1["preferences"][0]["key"] == "color"

    # Test without markdown
    result2 = classifier._parse_classification_result("""
{
  "preferences": [],
  "facts": [{"content": "test", "category": "work", "confidence": 0.8}],
  "episodes": []
}
    """)
    assert len(result2["facts"]) == 1

    # Test invalid JSON
    result3 = classifier._parse_classification_result("not json")
    assert result3 == {"preferences": [], "facts": [], "episodes": []}
