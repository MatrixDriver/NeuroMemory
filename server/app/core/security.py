"""API Key generation, hashing, and validation."""

import hashlib
import secrets

from server.app.core.config import get_settings


def generate_api_key() -> str:
    """Generate a new API key with nm_ prefix."""
    prefix = get_settings().api_key_prefix
    random_part = secrets.token_urlsafe(32)
    return f"{prefix}{random_part}"


def hash_api_key(api_key: str) -> str:
    """Hash an API key for storage (SHA-256)."""
    return hashlib.sha256(api_key.encode()).hexdigest()
