"""Tests for preferences CRUD."""

import pytest


@pytest.mark.asyncio
async def test_set_and_get_preference(client):
    """Set a preference and retrieve it."""
    # Set
    resp = await client.post(
        "/v1/preferences",
        json={"user_id": "u1", "key": "language", "value": "zh-CN"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["key"] == "language"
    assert data["value"] == "zh-CN"

    # Get
    resp = await client.get(
        "/v1/preferences/language", params={"user_id": "u1"}
    )
    assert resp.status_code == 200
    assert resp.json()["value"] == "zh-CN"


@pytest.mark.asyncio
async def test_upsert_preference(client):
    """Setting same key twice should update the value."""
    await client.post(
        "/v1/preferences",
        json={"user_id": "u1", "key": "theme", "value": "dark"},
    )
    resp = await client.post(
        "/v1/preferences",
        json={"user_id": "u1", "key": "theme", "value": "light"},
    )
    assert resp.status_code == 200
    assert resp.json()["value"] == "light"


@pytest.mark.asyncio
async def test_list_preferences(client):
    """List all preferences for a user."""
    await client.post(
        "/v1/preferences",
        json={"user_id": "u2", "key": "a", "value": "1"},
    )
    await client.post(
        "/v1/preferences",
        json={"user_id": "u2", "key": "b", "value": "2"},
    )
    resp = await client.get("/v1/preferences", params={"user_id": "u2"})
    assert resp.status_code == 200
    prefs = resp.json()["preferences"]
    assert len(prefs) >= 2


@pytest.mark.asyncio
async def test_delete_preference(client):
    """Delete a preference."""
    await client.post(
        "/v1/preferences",
        json={"user_id": "u3", "key": "to_delete", "value": "bye"},
    )
    resp = await client.delete(
        "/v1/preferences/to_delete", params={"user_id": "u3"}
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # Should be gone
    resp = await client.get(
        "/v1/preferences/to_delete", params={"user_id": "u3"}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_nonexistent_preference(client):
    """Get a preference that doesn't exist should return 404."""
    resp = await client.get(
        "/v1/preferences/nonexistent", params={"user_id": "u1"}
    )
    assert resp.status_code == 404
