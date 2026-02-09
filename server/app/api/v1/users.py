"""User memory overview endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.api.v1.schemas import UserMemoriesOverview
from server.app.db.session import get_db
from server.app.models.memory import Embedding, Preference
from server.app.services.auth import AuthContext, get_auth_context

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/{user_id}/memories", response_model=UserMemoriesOverview)
async def get_user_memories(
    user_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Get overview of all memories for a user."""
    pref_count = await db.scalar(
        select(func.count()).where(
            Preference.tenant_id == auth.tenant_id,
            Preference.user_id == user_id,
        )
    )
    emb_count = await db.scalar(
        select(func.count()).where(
            Embedding.tenant_id == auth.tenant_id,
            Embedding.user_id == user_id,
        )
    )
    return UserMemoriesOverview(
        user_id=user_id,
        preference_count=pref_count or 0,
        embedding_count=emb_count or 0,
    )
