"""API request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


# === Preferences ===
class PreferenceSet(BaseModel):
    user_id: str
    key: str
    value: str
    metadata: dict | None = None


class PreferenceGet(BaseModel):
    user_id: str
    key: str


class PreferenceResponse(BaseModel):
    user_id: str
    key: str
    value: str
    metadata: dict | None = None
    created_at: datetime
    updated_at: datetime


class PreferenceListResponse(BaseModel):
    user_id: str
    preferences: list[PreferenceResponse]


class PreferenceDeleteResponse(BaseModel):
    deleted: bool


# === Search ===
class SearchRequest(BaseModel):
    user_id: str
    query: str
    limit: int = Field(default=5, ge=1, le=50)
    memory_type: str | None = None


class SearchResult(BaseModel):
    id: str
    content: str
    memory_type: str
    metadata: dict | None = None
    score: float


class SearchResponse(BaseModel):
    user_id: str
    query: str
    results: list[SearchResult]


# === Memory ===
class MemoryAdd(BaseModel):
    user_id: str
    content: str
    memory_type: str = "general"
    metadata: dict | None = None


class MemoryResponse(BaseModel):
    id: str
    user_id: str
    content: str
    memory_type: str
    metadata: dict | None = None
    created_at: datetime


# === User memories overview ===
class UserMemoriesOverview(BaseModel):
    user_id: str
    preference_count: int
    embedding_count: int


# === Health ===
class HealthResponse(BaseModel):
    status: str
    database: str
    version: str = "2.0.0"


# === Tenant registration (simple) ===
class TenantRegister(BaseModel):
    name: str
    email: str


class TenantRegisterResponse(BaseModel):
    tenant_id: str
    api_key: str  # Only returned once at creation
    message: str


# === Error ===
class ErrorResponse(BaseModel):
    detail: str
