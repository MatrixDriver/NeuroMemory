"""Tenant registration endpoint (simple version for Phase 1)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.api.v1.schemas import TenantRegister, TenantRegisterResponse
from server.app.core.security import generate_api_key, hash_api_key
from server.app.db.session import get_db
from server.app.models.tenant import ApiKey, Tenant

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("/register", response_model=TenantRegisterResponse)
async def register_tenant(
    body: TenantRegister,
    db: AsyncSession = Depends(get_db),
):
    """Register a new tenant and get an API key."""
    # Check if email already exists
    existing = await db.execute(
        select(Tenant).where(Tenant.email == body.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    # Create tenant
    tenant = Tenant(name=body.name, email=body.email)
    db.add(tenant)
    await db.flush()

    # Create API key
    raw_key = generate_api_key()
    api_key = ApiKey(
        tenant_id=tenant.id,
        key_hash=hash_api_key(raw_key),
        key_prefix=raw_key[:8],
        name="default",
        permissions="read,write,admin",
    )
    db.add(api_key)

    return TenantRegisterResponse(
        tenant_id=str(tenant.id),
        api_key=raw_key,
        message="Save your API key - it won't be shown again.",
    )
