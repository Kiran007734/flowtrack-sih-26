from __future__ import annotations

from datetime import UTC, datetime
from socket import gethostname
from uuid import UUID

from app.db.session import SessionLocal
from app.models import JobExecution
from app.services.evc_reminders import queue_compliance_reminders, queue_evc_reminders
from app.services.ingestion import process_ingestion
from app.services.outbox import dispatch_pending_events, reset_stale_claims
from app.tasks.celery_app import celery_app


@celery_app.task(name="flowtrack.dispatch_outbox", bind=True)
def dispatch_outbox(self: object) -> dict[str, int]:
    worker_id = f"{gethostname()}:{getattr(getattr(self, 'request', None), 'id', 'scheduler')}"
    with SessionLocal() as session:
        recovered = reset_stale_claims(session)
        session.commit()
    processed = dispatch_pending_events(worker_id=worker_id)
    return {"recovered_claims": recovered, "processed": processed}


@celery_app.task(name="flowtrack.queue_evc_reminders", bind=True)
def queue_reminders(self: object) -> dict[str, int]:
    with SessionLocal() as session:
        queued = queue_evc_reminders(session)
        queued += queue_compliance_reminders(session)
        session.commit()
    return {"queued": queued}


@celery_app.task(name="flowtrack.diagnostic", bind=True)
def diagnostic_task(self: object) -> dict[str, str]:
    """A non-destructive task used to verify worker/database wiring."""

    task_id = str(getattr(getattr(self, "request", None), "id", None) or "direct-diagnostic")
    with SessionLocal() as session:
        execution = (
            session.query(JobExecution).filter(JobExecution.task_id == task_id).one_or_none()
        )
        if execution is None:
            execution = JobExecution(
                task_name="flowtrack.diagnostic",
                task_id=task_id,
                status="RUNNING",
            )
            session.add(execution)
            session.flush()
        result = {"status": "ok", "executed_at": datetime.now(UTC).isoformat()}
        execution.status = "SUCCEEDED"
        execution.result_summary = result
        execution.completed_at = datetime.now(UTC)
        session.commit()
    return result


@celery_app.task(
    name="flowtrack.process_guidance_ingestion",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def process_guidance_ingestion(self: object, run_id: str) -> dict[str, str]:
    """Worker entry point; the API deliberately retains an explicit sync fallback."""

    with SessionLocal() as session:
        item = process_ingestion(session, run_id=UUID(run_id))
        session.commit()
        return {"run_id": str(item.id), "status": item.status}
