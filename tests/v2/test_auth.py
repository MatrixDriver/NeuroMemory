"""Tests for API key authentication."""

import pytest


@pytest.mark.asyncio
async def test_no_auth_returns_401(unauth_client):
    """Request without API key should return 401."""
    resp = await unauth_client.get("/v1/preferences", params={"user_id": "u1"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_invalid_key_returns_401(unauth_client):
    """Request with invalid API key should return 401."""
    resp = await unauth_client.get(
        "/v1/preferences",
        params={"user_id": "u1"},
        headers={"Authorization": "Bearer nm_invalid_key_12345"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_valid_key_succeeds(client):
    """Request with valid API key should succeed."""
    resp = await client.get("/v1/preferences", params={"user_id": "u1"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_tenant_registration(unauth_client):
    """Register a new tenant and get API key."""
    resp = await unauth_client.post(
        "/v1/tenants/register",
        json={"name": "New Tenant", "email": "new@example.com"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["api_key"].startswith("nm_")
    assert "tenant_id" in data


@pytest.mark.asyncio
async def test_duplicate_email_returns_409(unauth_client):
    """Registering with same email twice should fail."""
    payload = {"name": "Dup", "email": "dup@example.com"}
    resp1 = await unauth_client.post("/v1/tenants/register", json=payload)
    assert resp1.status_code == 200
    resp2 = await unauth_client.post("/v1/tenants/register", json=payload)
    assert resp2.status_code == 409
