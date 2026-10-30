from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel, RowVersionRequest


class ObligationCreate(APIModel):
    application_id: UUID
    title: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    due_at: datetime | None = None
    timezone: str = Field(default="UTC", min_length=2, max_length=64)
    required_evidence: bool = True


class EvidenceSubmit(APIModel):
    document_id: UUID
    document_version_id: UUID
    comment: str | None = Field(default=None, max_length=2000)


class ReviewAction(APIModel):
    reason: str | None = Field(default=None, max_length=2000)


class ValidityCreate(APIModel):
    document_id: UUID
    document_version_id: UUID
    category: str = Field(min_length=2, max_length=128)
    issuing_authority: str | None = Field(default=None, max_length=255)
    issue_date: datetime | None = None
    expiry_date: datetime | None = None
    advance_notice_days: int = Field(default=30, ge=1, le=730)
    responsible_user_id: UUID | None = None


class ValidityAction(RowVersionRequest):
    document_version_id: UUID | None = None
