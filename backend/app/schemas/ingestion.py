from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel


class IngestionStart(APIModel):
    document_id: UUID
    document_version_id: UUID
    synchronous: bool = True


class ExtractionReview(APIModel):
    action: str = Field(pattern="^(approve|reject)$")
    reason: str | None = Field(default=None, max_length=2000)


class ExtractionCorrection(APIModel):
    corrected_text: str = Field(min_length=1, max_length=200000)
    reason: str = Field(min_length=2, max_length=2000)
