from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    ComplianceEvidence,
    ComplianceObligation,
    EvcChecklistItem,
    EvcReport,
    EvcVisit,
    EvcVisitPersonnel,
    OutboxEvent,
    User,
    ValidityRecord,
)
from app.services.audit import record_audit_event
from app.services.outbox import create_outbox_event


def _recipients(session: Session, visit: EvcVisit) -> list[str]:
    ids = {visit.coordinator_id}
    ids.update(
        session.scalars(
            select(EvcVisitPersonnel.user_id).where(
                EvcVisitPersonnel.visit_id == visit.id,
                EvcVisitPersonnel.status == "ASSIGNED",
            )
        )
    )
    return [
        str(user_id)
        for user_id in session.scalars(
            select(User.id).where(User.id.in_(ids), User.is_active.is_(True))
        )
    ]


def _queue(
    session: Session,
    *,
    visit: EvcVisit,
    kind: str,
    title: str,
    body: str,
    now: datetime,
) -> bool:
    recipients = _recipients(session, visit)
    if not recipients:
        return False
    local_day = now.astimezone(ZoneInfo(visit.timezone)).date().isoformat()
    key = f"evc-reminder:{visit.id}:{kind}:{local_day}"
    if session.scalar(select(OutboxEvent.id).where(OutboxEvent.idempotency_key == key)):
        return False
    create_outbox_event(
        session,
        event_type="EVC_REMINDER",
        aggregate_type="EVC_VISIT",
        aggregate_id=str(visit.id),
        aggregate_version=visit.row_version,
        payload={
            "application_id": str(visit.application_id),
            "recipient_user_ids": recipients,
            "title": title,
            "body": body,
            "reminder_kind": kind,
        },
        idempotency_key=key,
    )
    record_audit_event(
        session,
        actor=None,
        action="EVC_REMINDER_QUEUED",
        entity_type="EVC_VISIT",
        entity_id=str(visit.id),
        after_summary={"kind": kind, "recipient_count": len(recipients), "local_day": local_day},
    )
    return True


def queue_evc_reminders(session: Session, *, now: datetime | None = None) -> int:
    """Queue synthetic, in-app EVC reminders. This is safe to retry within a local day."""

    session.flush()
    now = now or datetime.now(UTC)
    settings = get_settings()
    lead = now + timedelta(hours=settings.evc_reminder_lead_hours)
    overdue = now - timedelta(hours=settings.evc_reminder_overdue_hours)
    queued = 0
    visits = list(session.scalars(select(EvcVisit).where(EvcVisit.status.not_in(("CANCELLED",)))))
    for visit in visits:
        if visit.status == "CONFIRMED" and now <= visit.scheduled_start <= lead:
            queued += _queue(
                session,
                visit=visit,
                kind="upcoming_visit",
                title="Upcoming synthetic EVC visit",
                body="A confirmed EVC visit is approaching.",
                now=now,
            )
        outstanding = session.scalar(
            select(EvcChecklistItem.id).where(
                EvcChecklistItem.visit_id == visit.id,
                EvcChecklistItem.status != "COMPLETED",
            )
        )
        if outstanding and visit.status not in {"COMPLETED", "CANCELLED"}:
            queued += _queue(
                session,
                visit=visit,
                kind="checklist",
                title="EVC checklist action required",
                body="A configured checklist item remains outstanding.",
                now=now,
            )
        reports = list(session.scalars(select(EvcReport).where(EvcReport.visit_id == visit.id)))
        if visit.status == "COMPLETED" and not reports:
            queued += _queue(
                session,
                visit=visit,
                kind="report_submission",
                title="EVC report required",
                body="Submit the synthetic visit report for review.",
                now=now,
            )
        if any(report.status == "SUBMITTED" for report in reports):
            queued += _queue(
                session,
                visit=visit,
                kind="report_review",
                title="EVC report awaiting review",
                body="A synthetic EVC report awaits authorized review.",
                now=now,
            )
        if any(report.status == "RETURNED" for report in reports):
            queued += _queue(
                session,
                visit=visit,
                kind="report_correction",
                title="EVC report returned",
                body="A returned synthetic report requires correction.",
                now=now,
            )
        if visit.status in {"CONFIRMED", "IN_PROGRESS"} and visit.scheduled_start < overdue:
            queued += _queue(
                session,
                visit=visit,
                kind="overdue_visit",
                title="Overdue EVC task",
                body="The configured synthetic visit timing requires escalation.",
                now=now,
            )
    return queued


def queue_compliance_reminders(session: Session, *, now: datetime | None = None) -> int:
    session.flush()
    now = now or datetime.now(UTC)
    queued = 0
    for obligation in session.scalars(
        select(ComplianceObligation).where(
            ComplianceObligation.status.not_in(("VERIFIED", "CLOSED"))
        )
    ):
        if obligation.due_at and obligation.due_at > now + timedelta(days=30):
            continue
        kind = (
            "overdue_obligation"
            if obligation.due_at and obligation.due_at < now
            else "missing_evidence"
            if obligation.status == "OUTSTANDING"
            else "evidence_review"
            if obligation.status == "SUBMITTED"
            else "correction"
        )
        day = now.astimezone(ZoneInfo(obligation.timezone)).date().isoformat()
        key = f"compliance-reminder:{obligation.id}:{kind}:{day}"
        if session.scalar(select(OutboxEvent.id).where(OutboxEvent.idempotency_key == key)):
            continue
        recipient = obligation.created_by_user_id
        if kind == "correction":
            latest = session.scalar(
                select(ComplianceEvidence)
                .where(ComplianceEvidence.obligation_id == obligation.id)
                .order_by(ComplianceEvidence.created_at.desc())
            )
            if latest is not None:
                recipient = latest.submitted_by_user_id
        create_outbox_event(
            session,
            event_type="COMPLIANCE_REMINDER",
            aggregate_type="COMPLIANCE_OBLIGATION",
            aggregate_id=str(obligation.id),
            aggregate_version=obligation.row_version,
            payload={
                "recipient_user_ids": [str(recipient)],
                "title": "Synthetic compliance action required",
                "body": "A configured compliance obligation requires attention.",
                "reminder_kind": kind,
            },
            idempotency_key=key,
        )
        record_audit_event(
            session,
            actor=None,
            action="COMPLIANCE_REMINDER_QUEUED",
            entity_type="COMPLIANCE_OBLIGATION",
            entity_id=str(obligation.id),
            after_summary={"kind": kind},
        )
        queued += 1
    for record in session.scalars(
        select(ValidityRecord).where(ValidityRecord.expiry_date.is_not(None))
    ):
        if record.renewal_status == "RENEWED" or record.responsible_user_id is None:
            continue
        assert record.expiry_date is not None
        if record.expiry_date > now + timedelta(days=record.advance_notice_days):
            continue
        kind = "expired_document" if record.expiry_date < now else "expiring_document"
        key = f"validity-reminder:{record.id}:{kind}:{now.date().isoformat()}"
        if session.scalar(select(OutboxEvent.id).where(OutboxEvent.idempotency_key == key)):
            continue
        create_outbox_event(
            session,
            event_type="COMPLIANCE_REMINDER",
            aggregate_type="VALIDITY_RECORD",
            aggregate_id=str(record.id),
            aggregate_version=None,
            payload={
                "recipient_user_ids": [str(record.responsible_user_id)],
                "title": "Synthetic document validity action required",
                "body": "A registered document is expiring or expired.",
                "reminder_kind": kind,
            },
            idempotency_key=key,
        )
        record_audit_event(
            session,
            actor=None,
            action="VALIDITY_REMINDER_QUEUED",
            entity_type="VALIDITY_RECORD",
            entity_id=str(record.id),
            after_summary={"kind": kind},
        )
        queued += 1
    return queued
