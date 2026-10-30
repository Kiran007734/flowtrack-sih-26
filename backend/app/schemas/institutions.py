from __future__ import annotations

from uuid import UUID

from app.schemas.common import APIModel


class InstitutionResponse(APIModel):
    id: UUID
    code: str
    name: str
    region_id: UUID
    is_active: bool
