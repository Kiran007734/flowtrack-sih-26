from __future__ import annotations

import json
from hashlib import sha256
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models import CommandIdempotency


def _request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(canonical.encode("utf-8")).hexdigest()


def replay_response(
    session: Session,
    *,
    actor_id: UUID,
    operation: str,
    idempotency_key: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Return the original response or reject a key reused for another request."""

    record = session.scalar(
        select(CommandIdempotency).where(
            CommandIdempotency.actor_id == actor_id,
            CommandIdempotency.operation == operation,
            CommandIdempotency.idempotency_key == idempotency_key,
        )
    )
    if record is None:
        return None
    if record.request_hash != _request_hash(payload):
        raise ConflictError(
            "This Idempotency-Key was already used with a different request payload",
            code="idempotency_key_reused",
        )
    return dict(record.response_body)


def record_response(
    session: Session,
    *,
    actor_id: UUID,
    operation: str,
    idempotency_key: str,
    payload: dict[str, Any],
    response_body: dict[str, Any],
    response_status: int,
) -> None:
    """Persist the response in the same transaction as the command effects."""

    session.add(
        CommandIdempotency(
            actor_id=actor_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request_hash=_request_hash(payload),
            response_status=response_status,
            response_body=response_body,
        )
    )
