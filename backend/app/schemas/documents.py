from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.schemas.common import APIModel


class DocumentVersionResponse(APIModel):
    id: UUID
    version_number: int
    original_filename: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str
    processing_status: str
    created_at: datetime


class DocumentResponse(APIModel):
    id: UUID
    institution_id: UUID
    application_id: UUID | None
    classification: str
    current_version_number: int
    status: str
    created_at: datetime
    versions: list[DocumentVersionResponse] = []
