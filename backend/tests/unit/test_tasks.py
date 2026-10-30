from __future__ import annotations

from app.db.seed import seed
from app.db.session import SessionLocal
from app.models import (
    Application,
    EvcChecklistItem,
    EvcVisit,
    JobExecution,
    Notification,
    OutboxEvent,
    User,
)
from app.services.evc_reminders import queue_evc_reminders
from app.services.outbox import dispatch_pending_events
from app.tasks.jobs import diagnostic_task
from sqlalchemy import select


def test_diagnostic_task_records_a_non_destructive_execution() -> None:
    result = diagnostic_task.run()
    assert result["status"] == "ok"
    with SessionLocal() as session:
        execution = session.scalar(
            select(JobExecution).where(JobExecution.task_id == "direct-diagnostic")
        )
        assert execution is not None
        assert execution.status == "SUCCEEDED"


def test_evc_reminders_are_deduplicated_delivered_and_suppressed() -> None:
    from datetime import UTC, datetime, timedelta

    seed()
    with SessionLocal() as session:
        coordinator = session.scalar(select(User).where(User.email == "evc.south@example.org"))
        assert coordinator is not None
        target = session.scalar(
            select(Application).where(Application.reference_number == "DEMO-APP-BETA-EVC")
        )
        assert target is not None
        visit = EvcVisit(
            application_id=target.id,
            institution_id=target.institution_id,
            region_id=target.assigned_region_id,
            coordinator_id=coordinator.id,
            status="CONFIRMED",
            scheduled_start=datetime.now(UTC) + timedelta(hours=2),
            duration_minutes=60,
            timezone="UTC",
            visit_mode="ONSITE",
            location="Synthetic reminder campus",
            row_version=2,
        )
        session.add(visit)
        session.flush()
        session.add(EvcChecklistItem(visit_id=visit.id, label="Mandatory synthetic item"))
        now = datetime.now(UTC)
        assert queue_evc_reminders(session, now=now) == 2
        assert queue_evc_reminders(session, now=now) == 0
        session.commit()
    assert dispatch_pending_events("reminder-test") == 2
    with SessionLocal() as session:
        assert (
            session.scalar(select(Notification).where(Notification.user_id == coordinator.id))
            is not None
        )
        visit = session.scalar(
            select(EvcVisit).where(EvcVisit.location == "Synthetic reminder campus")
        )
        assert visit is not None
        visit.status = "CANCELLED"
        session.commit()
    with SessionLocal() as session:
        assert queue_evc_reminders(session, now=datetime.now(UTC) + timedelta(days=1)) == 0
        assert (
            session.scalar(select(OutboxEvent).where(OutboxEvent.event_type == "EVC_REMINDER"))
            is not None
        )


def test_overdue_reminder_retries_after_delivery_failure() -> None:
    from datetime import UTC, datetime, timedelta

    seed()
    with SessionLocal() as session:
        coordinator = session.scalar(select(User).where(User.email == "evc.south@example.org"))
        target = session.scalar(
            select(Application).where(Application.reference_number == "DEMO-APP-BETA-EVC")
        )
        assert coordinator is not None and target is not None
        visit = EvcVisit(
            application_id=target.id,
            institution_id=target.institution_id,
            region_id=target.assigned_region_id,
            coordinator_id=coordinator.id,
            status="IN_PROGRESS",
            scheduled_start=datetime.now(UTC) - timedelta(days=2),
            duration_minutes=60,
            timezone="UTC",
            visit_mode="ONSITE",
            location="Synthetic overdue campus",
            row_version=3,
        )
        session.add(visit)
        session.flush()
        visit_id = str(visit.id)
        assert queue_evc_reminders(session, now=datetime.now(UTC)) == 1
        session.flush()
        event = session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == visit_id,
                OutboxEvent.event_type == "EVC_REMINDER",
            )
        )
        assert event is not None
        assert event.payload["reminder_kind"] == "overdue_visit"
        event.payload = {**event.payload, "recipient_user_ids": ["not-a-uuid"]}
        session.commit()
    assert dispatch_pending_events("retry-test") == 0
    with SessionLocal() as session:
        retried = session.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == visit_id))
        assert retried is not None
        assert retried.status == "PENDING"
        assert retried.attempt_count == 1
