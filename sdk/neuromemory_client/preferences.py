"""Preferences sub-client."""

from __future__ import annotations

import httpx


class PreferencesClient:
    def __init__(self, http: httpx.Client):
        self._http = http

    def set(
        self,
        user_id: str,
        key: str,
        value: str,
        metadata: dict | None = None,
    ) -> dict:
        """Set a preference (upsert)."""
        resp = self._http.post(
            "/preferences",
            json={"user_id": user_id, "key": key, "value": value, "metadata": metadata},
        )
        resp.raise_for_status()
        return resp.json()

    def get(self, user_id: str, key: str) -> dict:
        """Get a single preference."""
        resp = self._http.get("/preferences/" + key, params={"user_id": user_id})
        resp.raise_for_status()
        return resp.json()

    def list(self, user_id: str) -> list[dict]:
        """List all preferences for a user."""
        resp = self._http.get("/preferences", params={"user_id": user_id})
        resp.raise_for_status()
        return resp.json()["preferences"]

    def delete(self, user_id: str, key: str) -> bool:
        """Delete a preference. Returns True if deleted."""
        resp = self._http.delete("/preferences/" + key, params={"user_id": user_id})
        resp.raise_for_status()
        return resp.json()["deleted"]
