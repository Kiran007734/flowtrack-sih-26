from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import CommunicationDraft, Notification, OutboxEvent
from app.services.audit import record_audit_event


def create_outbox_event(
    session: Session,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    aggregate_version: int | None,
    payload: dict[str, Any],
    idempotency_key: str,
) -> OutboxEvent:
    existing = session.scalar(
        select(OutboxEvent).where(OutboxEvent.idempotency_key == idempotency_key)
    )
    if existing:
        return existing
    event = OutboxEvent(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        aggregate_version=aggregate_version,
        payload=payload,
        idempotency_key=idempotency_key,
        status="PENDING",
        next_attempt_at=datetime.now(UTC),
    )
    session.add(event)
    return event


def claim_next_outbox_event(session: Session, worker_id: str) -> UUID | None:
    now = datetime.now(UTC)
    event = session.scalar(
        select(OutboxEvent)
        .where(
            OutboxEvent.status == "PENDING",
            or_(OutboxEvent.next_attempt_at.is_(None), OutboxEvent.next_attempt_at <= now),
        )
        .order_by(OutboxEvent.created_at, OutboxEvent.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if event is None:
        return None
    event.status = "PROCESSING"
    event.claimed_at = now
    event.claimed_by = worker_id
    session.flush()
    return event.id


def _create_in_app_notifications(session: Session, event: OutboxEvent) -> None:
    recipient_ids = event.payload.get("recipient_user_ids", [])
    if not isinstance(recipient_ids, list):
        raise ValueError("recipient_user_ids must be a list")
    for raw_user_id in recipient_ids:
        user_id = UUID(str(raw_user_id))
        exists = session.scalar(
            select(Notification.id).where(
                Notification.user_id == user_id,
                Notification.outbox_event_id == event.id,
            )
        )
        if exists is None:
            session.add(
                Notification(
                    user_id=user_id,
                    outbox_event_id=event.id,
                    title=str(event.payload.get("title", "FlowTrack notification"))[:255],
                    body=str(event.payload.get("body", ""))[:4000],
                    status="UNREAD",
                )
            )


def dispatch_claimed_event(event_id: UUID) -> bool:
    """Process one claimed event. The business transaction already committed before this starts."""

    settings = get_settings()
    try:
        with SessionLocal() as session:
            event = session.get(OutboxEvent, event_id, with_for_update=True)
            if event is None or event.status == "PROCESSED":
                return False
            if event.status not in {"PENDING", "PROCESSING"}:
                return False
            if event.event_type in {
                "APPLICATION_SUBMITTED",
                "APPLICATION_RETURNED",
                "EVC_REMINDER",
                "COMPLIANCE_REMINDER",
            }:
                _create_in_app_notifications(session, event)
            elif event.event_type == "SIMULATED_COMMUNICATION_DISPATCH":
                draft = session.get(
                    CommunicationDraft, UUID(event.aggregate_id), with_for_update=True
                )
                if draft is None or draft.status != "QUEUED_SIMULATED":
                    raise ValueError("Communication draft is not queued for simulated dispatch")
                draft.status = "SIMULATED_DELIVERED"
                draft.dispatched_at = datetime.now(UTC)
                record_audit_event(
                    session,
                    actor=None,
                    action="COMMUNICATION_SIMULATED_DELIVERY_COMPLETED",
                    entity_type="COMMUNICATION_DRAFT",
                    entity_id=str(draft.id),
                    after_summary={"real_delivery": False},
                )
            elif event.event_type not in {
                "APPLICATION_DRAFT_CREATED",
                "APPLICATION_DRAFT_UPDATED",
                "WORKFLOW_TRANSITIONED",
                "COMMITTEE_REVIEW_FINALIZED",
                "COMPLIANCE_EVIDENCE_SUBMITTED",
                "EVC_VISIT_PROPOSED",
                "EVC_VISIT_CONFIRMED",
                "EVC_VISIT_STARTED",
                "EVC_VISIT_COMPLETED",
                "EVC_VISIT_CANCELLED",
                "EVC_VISIT_CANCELED",
                "EVC_REPORT_SUBMITTED",
                "EVC_REPORT_RETURNED",
                "EVC_REPORT_RESUBMITED",
                "EVC_REPORT_ACCEPTED",
                "EVC_REPORT_CLOSED",
                "EVC_EVIDENCE_LINKED",
                "EVC_EVIDENCE_VERIFIED",
                "EVC_EVIDENCE_REJECTED",
            }:
                raise ValueError(f"Unsupported outbox event type: {event.event_type}")
            event.status = "PROCESSED"
            event.processed_at = datetime.now(UTC)
            event.claimed_at = None
            event.claimed_by = None
            event.last_error = None
            if event.event_type in {"EVC_REMINDER", "COMPLIANCE_REMINDER"}:
                record_audit_event(
                    session,
                    actor=None,
                    action="EVC_REMINDER_DELIVERED",
                    entity_type="OUTBOX_EVENT",
                    entity_id=str(event.id),
                    after_summary={
                        "delivery": "in_app",
                        "recipient_count": len(event.payload.get("recipient_user_ids", [])),
                    },
                )
            session.commit()
            return True
    except Exception as exc:
        with SessionLocal() as session:
            event = session.get(OutboxEvent, event_id, with_for_update=True)
            if event is None or event.status == "PROCESSED":
                return False
            event.attempt_count += 1
            event.last_error = str(exc)[:1000]
            if event.event_type in {"EVC_REMINDER", "COMPLIANCE_REMINDER"}:
                record_audit_event(
                    session,
                    actor=None,
                    action="EVC_REMINDER_DELIVERY_FAILED",
                    entity_type="OUTBOX_EVENT",
                    entity_id=str(event.id),
                    outcome="FAILURE",
                    reason=event.last_error,
                )
            event.claimed_at = None
            event.claimed_by = None
            if event.attempt_count >= settings.outbox_max_attempts:
                event.status = "FAILED"
                event.next_attempt_at = None
            else:
                event.status = "PENDING"
                event.next_attempt_at = datetime.now(UTC) + timedelta(
                    seconds=min(300, 2**event.attempt_count)
                )
            session.commit()
        return False


def dispatch_pending_events(worker_id: str, batch_size: int = 50) -> int:
    """Claim small transactions, then dispatch outside the claiming transaction."""

    processed = 0
    for _ in range(batch_size):
        with SessionLocal() as session:
            event_id = claim_next_outbox_event(session, worker_id)
            session.commit()
        if event_id is None:
            break
        if dispatch_claimed_event(event_id):
            processed += 1
    return processed


def reset_stale_claims(session: Session, older_than_minutes: int = 10) -> int:
    """Make abandoned worker claims retryable; called by the controlled scheduler."""

    cutoff = datetime.now(UTC) - timedelta(minutes=older_than_minutes)
    events = list(
        session.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.status == "PROCESSING", OutboxEvent.claimed_at < cutoff)
            .with_for_update(skip_locked=True)
        )
    )
    for event in events:
        event.status = "PENDING"
        event.claimed_at = None
        event.claimed_by = None
        event.next_attempt_at = datetime.now(UTC)
    return len(events)
