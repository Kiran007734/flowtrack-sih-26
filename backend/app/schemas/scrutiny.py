from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel, RowVersionRequest


class FindingInput(APIModel):
    requirement_reference: str = Field(min_length=2, max_length=255)
    assessment: str = Field(pattern="^(ADEQUATE|INADEQUATE|CLARIFICATION_REQUIRED)$")
    comment: str = Field(min_length=2, max_length=4000)
    references: dict[str, str] = Field(default_factory=dict)


class ReviewDraftRequest(APIModel):
    summary: str | None = Field(default=None, max_length=4000)
    findings: list[FindingInput] = Field(default_factory=list, max_length=50)


class ReviewResponse(APIModel):
    id: UUID
    application_id: UUID
    reviewer_id: UUID
    status: str
    summary: str | None
    submitted_at: datetime | None
    created_at: datetime


class DeficiencyItem(APIModel):
    description: str = Field(min_length=2, max_length=4000)
    finding_id: UUID | None = None


class ReturnRequest(RowVersionRequest):
    reason: str = Field(min_length=2, max_length=2000)
    deficiencies: list[DeficiencyItem] = Field(min_length=1, max_length=25)


class DeficiencyResponseRequest(APIModel):
    response_text: str = Field(min_length=2, max_length=4000)
    document_id: UUID | None = None


class DeficiencyResponseModel(APIModel):
    id: UUID
    application_id: UUID
    identifier: str
    status: str
    description: str
    finding_id: UUID | None
    created_at: datetime
    resolved_at: datetime | None
    responses: list[dict[str, str | None]] = Field(default_factory=list)


class AssignmentCreateRequest(APIModel):
    reviewer_id: UUID
    responsibility: str = Field(default="SCRUTINY", pattern="^SCRUTINY$")
    valid_until: datetime | None = None
    reason: str | None = Field(default=None, max_length=2000)


class AssignmentResponse(APIModel):
    id: UUID
    application_id: UUID
    reviewer_id: UUID
    assigned_by_user_id: UUID
    responsibility: str
    status: str
    valid_from: datetime
    valid_until: datetime | None
    revoked_at: datetime | None
    reason: str | None
