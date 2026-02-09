"""Authentication service - API key validation."""

import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.core.security import hash_api_key
from server.app.db.session import get_db
from server.app.models.tenant import ApiKey

security_scheme = HTTPBearer()


@dataclass
class AuthContext:
    tenant_id: uuid.UUID
    api_key_id: uuid.UUID
    permissions: list[str]

    def has_permission(self, perm: str) -> bool:
        return perm in self.permissions or "admin" in self.permissions


async def get_auth_context(
    credentials: HTTPAuthorizationCredentials = Security(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    """Validate API key and return auth context."""
    api_key = credentials.credentials
    key_hash = hash_api_key(api_key)

    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
    )
    api_key_record = result.scalar_one_or_none()

    if not api_key_record:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")

    return AuthContext(
        tenant_id=api_key_record.tenant_id,
        api_key_id=api_key_record.id,
        permissions=api_key_record.permissions.split(","),
    )


def require_permission(perm: str):
    """Dependency that checks for a specific permission."""

    async def checker(auth: AuthContext = Depends(get_auth_context)):
        if not auth.has_permission(perm):
            raise HTTPException(
                status_code=403,
                detail=f"Missing required permission: {perm}",
            )
        return auth

    return checker
