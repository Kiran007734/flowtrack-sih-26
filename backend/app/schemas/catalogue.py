from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel


class GuidanceSourceCreate(APIModel):
    key: str = Field(min_length=2, max_length=96, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    title: str = Field(min_length=2, max_length=255)
    source_type: str = Field(min_length=2, max_length=64)
    issuing_organization: str | None = Field(default=None, max_length=255)
    source_reference: str | None = Field(default=None, max_length=1024)
    provenance: dict[str, Any] = Field(default_factory=dict)
    version_label: str = Field(min_length=1, max_length=128)
    effective_date: datetime | None = None
    content_hash: str | None = Field(default=None, max_length=128)
    upload_metadata: dict[str, Any] = Field(default_factory=dict)
    verification_status: Literal["SYNTHETIC_DEMONSTRATION", "VERIFIED_OFFICIAL"] = (
        "SYNTHETIC_DEMONSTRATION"
    )


class GuidanceVersionCreate(APIModel):
    version_label: str = Field(min_length=1, max_length=128)
    effective_date: datetime | None = None
    content_hash: str | None = Field(default=None, max_length=128)
    upload_metadata: dict[str, Any] = Field(default_factory=dict)
    verification_status: Literal["SYNTHETIC_DEMONSTRATION", "VERIFIED_OFFICIAL"] = (
        "SYNTHETIC_DEMONSTRATION"
    )


class LifecycleAction(APIModel):
    reason: str | None = Field(default=None, max_length=2000)


class RequirementCreate(APIModel):
    stable_identifier: str = Field(min_length=2, max_length=128, pattern=r"^[A-Z0-9][A-Z0-9_.-]*$")
    source_version_id: UUID
    title: str = Field(min_length=2, max_length=255)
    description: str = Field(min_length=2, max_length=8000)
    category: str = Field(min_length=2, max_length=64)
    module_key: str = Field(min_length=2, max_length=64)
    section_reference: str | None = Field(default=None, max_length=255)
    applicability_conditions: dict[str, Any] = Field(default_factory=dict)
    evidence_metadata: dict[str, Any] = Field(default_factory=dict)
    severity: str | None = Field(default=None, max_length=32)
    supersedes_requirement_id: UUID | None = None


class MappingCreate(APIModel):
    requirement_id: UUID
    application_id: UUID
    document_id: UUID
    document_version_id: UUID
    evc_evidence_link_id: UUID | None = None
    compliance_evidence_id: UUID | None = None
    explanation: str = Field(min_length=2, max_length=4000)
    supersedes_mapping_id: UUID | None = None
