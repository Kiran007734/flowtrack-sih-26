from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel, RowVersionRequest


class VisitCreate(APIModel):
    application_id: UUID
    scheduled_start: datetime
    duration_minutes: int = Field(ge=15, le=1440)
    timezone: str = Field(min_length=2, max_length=64)
    visit_mode: str = Field(default="ONSITE", pattern="^(ONSITE|REMOTE)$")
    location: str = Field(min_length=2, max_length=512)
    notes: str | None = Field(default=None, max_length=4000)


class VisitResponse(APIModel):
    id: UUID
    application_id: UUID
    coordinator_id: UUID
    status: str
    scheduled_start: datetime
    duration_minutes: int
    timezone: str
    visit_mode: str
    location: str
    notes: str | None
    row_version: int


class VisitAction(RowVersionRequest):
    reason: str | None = Field(default=None, max_length=2000)


class PersonnelRequest(APIModel):
    user_id: UUID
    role: str = Field(default="MEMBER", max_length=64)


class ChecklistRequest(APIModel):
    label: str = Field(min_length=2, max_length=512)
    note: str | None = Field(default=None, max_length=2000)


class ReportRequest(APIModel):
    summary: str = Field(min_length=2, max_length=4000)


class ChecklistAction(APIModel):
    note: str | None = Field(default=None, max_length=2000)


class ReportAction(APIModel):
    reason: str | None = Field(default=None, max_length=2000)


class EvidenceLinkRequest(APIModel):
    document_id: UUID
    document_version_id: UUID
    purpose: str = Field(min_length=2, max_length=128)
    comment: str | None = Field(default=None, max_length=2000)


class EvidenceAction(APIModel):
    reason: str | None = Field(default=None, max_length=2000)


class EvidenceResponse(APIModel):
    id: UUID
    visit_id: UUID
    document_id: UUID
    document_version_id: UUID
    purpose: str
    status: str
    comment: str | None
    verified_by_user_id: UUID | None
    verified_at: datetime | None
    created_at: datetime
