from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MessageResponse(APIModel):
    message: str


class PaginatedResponse(APIModel):
    items: list[Any]
    next_cursor: str | None = None


class ActorResponse(APIModel):
    id: UUID
    email: str
    display_name: str
    is_active: bool
    roles: list[str]


class AuditEventResponse(APIModel):
    id: UUID
    action: str
    entity_type: str
    entity_id: str
    outcome: str
    reason: str | None
    correlation_id: str | None
    created_at: datetime
    actor_id: UUID | None
    actor_context: dict[str, Any]
    before_summary: dict[str, Any] | None
    after_summary: dict[str, Any] | None


class RowVersionRequest(APIModel):
    row_version: int = Field(ge=1)
