from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery(
    "flowtrack",
    broker=settings.effective_celery_broker_url,
    backend=settings.effective_celery_result_backend,
    include=["app.tasks.jobs"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=settings.timezone,
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "dispatch-durable-outbox": {
            "task": "flowtrack.dispatch_outbox",
            "schedule": 30.0,
        },
        "queue-evc-reminders": {
            "task": "flowtrack.queue_evc_reminders",
            "schedule": 300.0,
        },
    },
)
