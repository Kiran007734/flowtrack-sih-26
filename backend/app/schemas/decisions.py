from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel


class DecisionCreate(APIModel):
    outcome: str = Field(pattern="^(APPROVED|REJECTED|RETURNED|DEFERRED)$")
    rationale: str = Field(min_length=5, max_length=10000)
    row_version: int = Field(ge=1)


class CommunicationCreate(APIModel):
    decision_id: UUID | None = None
    subject: str = Field(min_length=2, max_length=255)
    body: str = Field(min_length=2, max_length=20000)


class CommunicationEdit(CommunicationCreate):
    pass
