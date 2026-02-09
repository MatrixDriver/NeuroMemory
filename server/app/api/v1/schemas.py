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


# === Graph ===
class NodeCreate(BaseModel):
    """Request to create a graph node."""

    node_type: str = Field(..., description="Type of node: User, Memory, Concept, Entity")
    node_id: str = Field(..., description="Unique identifier for the node")
    properties: dict | None = Field(None, description="Additional node properties")


class EdgeCreate(BaseModel):
    """Request to create a graph edge."""

    source_type: str = Field(..., description="Source node type")
    source_id: str = Field(..., description="Source node ID")
    edge_type: str = Field(..., description="Edge type: HAS_MEMORY, MENTIONS, etc.")
    target_type: str = Field(..., description="Target node type")
    target_id: str = Field(..., description="Target node ID")
    properties: dict | None = Field(None, description="Edge properties")


class NodeResponse(BaseModel):
    """Response for a graph node."""

    id: str
    tenant_id: str
    node_type: str
    node_id: str
    properties: dict | None
    created_at: datetime


class EdgeResponse(BaseModel):
    """Response for a graph edge."""

    id: str
    tenant_id: str
    source_type: str
    source_id: str
    edge_type: str
    target_type: str
    target_id: str
    properties: dict | None
    created_at: datetime


class NeighborsRequest(BaseModel):
    """Request to get neighboring nodes."""

    node_type: str
    node_id: str
    edge_types: list[str] | None = None
    direction: str = Field("both", pattern="^(in|out|both)$")
    limit: int = Field(10, ge=1, le=100)


class PathRequest(BaseModel):
    """Request to find path between nodes."""

    source_type: str
    source_id: str
    target_type: str
    target_id: str
    max_depth: int = Field(3, ge=1, le=6)


class GraphQueryRequest(BaseModel):
    """Request for custom Cypher query."""

    cypher: str = Field(..., description="Cypher query (must include tenant_id filter)")
    params: dict | None = Field(None, description="Query parameters")


class GraphQueryResponse(BaseModel):
    """Response for graph query."""

    results: list[dict]
    count: int
