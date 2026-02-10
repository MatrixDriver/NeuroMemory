"""Pydantic schemas for conversation API"""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class MessageCreate(BaseModel):
    """Single message creation request"""

    role: str = Field(
        ...,
        description="Message role: user, assistant, or system",
        examples=["user", "assistant"]
    )
    content: str = Field(
        ...,
        min_length=1,
        description="Message content"
    )
    metadata: Optional[Dict] = Field(
        None,
        description="Additional metadata"
    )

    @field_validator('role')
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate role is one of allowed values"""
        allowed_roles = {"user", "assistant", "system"}
        if v not in allowed_roles:
            raise ValueError(f"Role must be one of {allowed_roles}")
        return v


class ConversationMessageRequest(BaseModel):
    """Request to add a single conversation message"""

    user_id: str = Field(..., description="User identifier")
    session_id: Optional[str] = Field(
        None,
        description="Session ID (auto-generated if not provided)"
    )
    role: str = Field(..., description="Message role")
    content: str = Field(..., description="Message content")
    metadata: Optional[Dict] = Field(None, description="Additional metadata")

    @field_validator('role')
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed_roles = {"user", "assistant", "system"}
        if v not in allowed_roles:
            raise ValueError(f"Role must be one of {allowed_roles}")
        return v


class ConversationBatchRequest(BaseModel):
    """Request to add multiple messages in batch"""

    user_id: str = Field(..., description="User identifier")
    session_id: Optional[str] = Field(
        None,
        description="Session ID (auto-generated if not provided)"
    )
    messages: List[MessageCreate] = Field(
        ...,
        min_length=1,
        description="List of messages to add"
    )

    @field_validator('messages')
    @classmethod
    def validate_messages(cls, v: List[MessageCreate]) -> List[MessageCreate]:
        """Ensure at least one message"""
        if not v:
            raise ValueError("Must provide at least one message")
        return v


class ConversationMessageResponse(BaseModel):
    """Response for a single conversation message"""

    id: UUID
    user_id: str
    session_id: str
    role: str
    content: str
    metadata_: Optional[Dict] = Field(None, serialization_alias="metadata")
    extracted: bool = False
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class ConversationBatchResponse(BaseModel):
    """Response for batch message creation"""

    session_id: str
    messages_added: int
    message_ids: List[UUID]


class ConversationSessionResponse(BaseModel):
    """Response for conversation session info"""

    id: UUID
    user_id: str
    session_id: str
    title: Optional[str] = None
    summary: Optional[str] = None
    message_count: int
    last_message_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationHistoryResponse(BaseModel):
    """Response for conversation history"""

    session_id: str
    message_count: int
    messages: List[ConversationMessageResponse]


class ConversationSessionListResponse(BaseModel):
    """Response for listing conversation sessions"""

    total: int
    sessions: List[ConversationSessionResponse]


class AutoExtractConfig(BaseModel):
    """Configuration for automatic memory extraction"""

    user_id: str = Field(..., description="User identifier")
    trigger: str = Field(
        "message_count",
        description="Trigger type: message_count or time_interval"
    )
    threshold: int = Field(
        10,
        ge=1,
        description="Threshold value (number of messages or minutes)"
    )
    async_mode: bool = Field(
        True,
        description="Whether to run extraction asynchronously"
    )

    @field_validator('trigger')
    @classmethod
    def validate_trigger(cls, v: str) -> str:
        allowed = {"message_count", "time_interval"}
        if v not in allowed:
            raise ValueError(f"Trigger must be one of {allowed}")
        return v


class ExtractMemoriesRequest(BaseModel):
    """Request to extract memories from conversations"""

    user_id: str = Field(..., description="User identifier")
    session_id: Optional[str] = Field(
        None,
        description="Session ID (if None, extract from all sessions)"
    )
    force: bool = Field(
        False,
        description="Force re-extraction even if already extracted"
    )


class ExtractMemoriesResponse(BaseModel):
    """Response for memory extraction"""

    task_id: Optional[str] = None
    status: str = Field(..., description="completed or pending")
    preferences_extracted: int = 0
    facts_extracted: int = 0
    episodes_extracted: int = 0
    documents_extracted: int = 0
    messages_processed: int = 0
