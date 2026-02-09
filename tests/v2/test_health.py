"""Tests for health check and root endpoints."""

import pytest


@pytest.mark.asyncio
async def test_root(unauth_client):
    """Root endpoint should return service info."""
    resp = await unauth_client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "NeuroMemory"
    assert data["version"] == "2.0.0"


@pytest.mark.asyncio
async def test_health(unauth_client):
    """Health endpoint should return status."""
    resp = await unauth_client.get("/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "database" in data
