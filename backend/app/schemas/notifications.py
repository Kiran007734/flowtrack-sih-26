from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.schemas.common import APIModel


class NotificationResponse(APIModel):
    id: UUID
    title: str
    body: str
    status: str
    created_at: datetime
    read_at: datetime | None
