from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent
from app.permissions.access import Principal


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))


def record_audit_event(
    session: Session,
    *,
    actor: Principal | None,
    action: str,
    entity_type: str,
    entity_id: str,
    outcome: str = "SUCCESS",
    reason: str | None = None,
    correlation_id: str | None = None,
    before_summary: dict[str, Any] | None = None,
    after_summary: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append a redacted, application-level audit event in the caller's transaction."""

    previous = session.scalar(
        select(AuditEvent).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(1)
    )
    event_id = uuid4()
    actor_context = {
        "role_keys": sorted(actor.role_keys) if actor else [],
        "scope_types": sorted({grant.scope_type for grant in actor.grants}) if actor else [],
    }
    event_body = {
        "id": str(event_id),
        "timestamp": datetime.now(UTC).isoformat(),
        "actor_id": str(actor.user.id) if actor else None,
        "actor_context": actor_context,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "outcome": outcome,
        "reason": reason,
        "correlation_id": correlation_id,
        "before": before_summary,
        "after": after_summary,
        "previous_hash": previous.event_hash if previous else None,
    }
    event = AuditEvent(
        id=event_id,
        actor_id=actor.user.id if actor else None,
        actor_context=actor_context,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        outcome=outcome,
        reason=reason,
        correlation_id=correlation_id,
        before_summary=before_summary,
        after_summary=after_summary,
        previous_hash=previous.event_hash if previous else None,
        event_hash=sha256(_canonical_json(event_body).encode("utf-8")).hexdigest(),
    )
    session.add(event)
    return event
