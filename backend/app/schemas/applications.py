from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel, RowVersionRequest


class ApplicationCreate(APIModel):
    institution_id: UUID
    application_type: str = Field(min_length=2, max_length=128)
    title: str = Field(min_length=2, max_length=255)
    workflow_template_key: str = Field(default="SCRUTINY_ONLY", min_length=2, max_length=96)
    data: dict[str, Any] = Field(default_factory=dict)


class ApplicationUpdate(RowVersionRequest):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    application_type: str | None = Field(default=None, min_length=2, max_length=128)
    data: dict[str, Any] | None = None


class ApplicationListFilters(APIModel):
    """Validated query contract for the scoped application work queue."""

    search: str | None = Field(default=None, max_length=255)
    institution_id: UUID | None = None
    status: str | None = Field(default=None, max_length=32)
    stage: str | None = Field(default=None, max_length=96)
    created_from: datetime | None = None
    created_to: datetime | None = None
    sort_by: str = "created_at"
    sort_direction: str = "desc"


class ApplicationResponse(APIModel):
    id: UUID
    institution_id: UUID
    assigned_region_id: UUID
    workflow_template_version_id: UUID
    reference_number: str
    application_type: str
    title: str
    status: str
    current_stage_key: str
    submitted_at: datetime | None
    current_version_number: int
    row_version: int
    created_at: datetime
    updated_at: datetime


class ApplicationDetailResponse(ApplicationResponse):
    latest_data: dict[str, Any]


class ApplicationVersionResponse(APIModel):
    id: UUID
    version_number: int
    data: dict[str, Any]
    checksum: str
    is_submission_snapshot: bool
    created_at: datetime
    submitted_at: datetime | None


class StageHistoryResponse(APIModel):
    id: UUID
    sequence: int
    transition_key: str
    from_stage_key: str | None
    to_stage_key: str
    actor_id: UUID
    comment: str | None
    facts: dict[str, Any]
    created_at: datetime


class TransitionEvaluationResponse(APIModel):
    transition_key: str
    allowed: bool
    reason_code: str
    explanation: str
    missing_prerequisites: list[str]
    required_permission: str | None
    applicable_workflow_version: UUID
    to_stage_key: str | None


class TransitionExecuteRequest(RowVersionRequest):
    comment: str | None = Field(default=None, max_length=2000)
