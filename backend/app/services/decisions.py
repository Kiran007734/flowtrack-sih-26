# ruff: noqa: E501, E701, E702
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models import Application, ApplicationDecision, CommunicationDraft
from app.permissions.access import Principal, require_application_access, require_permission
from app.services.audit import record_audit_event
from app.services.outbox import create_outbox_event


def _application(session: Session, application_id: UUID, principal: Principal) -> Application:
    item = session.get(Application, application_id)
    if not item:
        raise NotFoundError("The requested application was not found")
    require_application_access(principal, item)
    return item


def record_decision(
    session: Session,
    *,
    application_id: UUID,
    outcome: str,
    rationale: str,
    row_version: int,
    principal: Principal,
    correlation_id: str | None,
) -> ApplicationDecision:
    require_permission(principal, "decision.record")
    app = _application(session, application_id, principal)
    if app.row_version != row_version:
        raise ConflictError(
            "The application has changed; refresh before recording a decision",
            code="stale_row_version",
        )
    if session.scalar(
        select(ApplicationDecision).where(
            ApplicationDecision.application_id == app.id,
            ApplicationDecision.workflow_stage_key == app.current_stage_key,
        )
    ):
        raise ConflictError(
            "A decision already exists for this workflow stage", code="decision_exists"
        )
    item = ApplicationDecision(
        id=uuid4(),
        application_id=app.id,
        workflow_template_version_id=app.workflow_template_version_id,
        workflow_stage_key=app.current_stage_key,
        outcome=outcome,
        rationale=rationale,
        decided_by_user_id=principal.user.id,
        application_row_version=app.row_version,
        decided_at=datetime.now(UTC),
    )
    session.add(item)
    session.flush()
    record_audit_event(
        session,
        actor=principal,
        action="APPLICATION_DECISION_RECORDED",
        entity_type="APPLICATION_DECISION",
        entity_id=str(item.id),
        correlation_id=correlation_id,
        after_summary={"outcome": outcome, "advisory_committee_not_transition": True},
    )
    return item


def create_communication(
    session: Session,
    *,
    application_id: UUID,
    decision_id: UUID | None,
    subject: str,
    body: str,
    principal: Principal,
    correlation_id: str | None,
) -> CommunicationDraft:
    require_permission(principal, "communication.manage")
    app = _application(session, application_id, principal)
    if decision_id:
        decision = session.get(ApplicationDecision, decision_id)
        if not decision or decision.application_id != app.id:
            raise NotFoundError("The requested decision was not found")
    item = CommunicationDraft(
        id=uuid4(),
        application_id=app.id,
        decision_id=decision_id,
        subject=subject,
        body=body,
        status="DRAFT",
        created_by_user_id=principal.user.id,
    )
    session.add(item)
    record_audit_event(
        session,
        actor=principal,
        action="COMMUNICATION_DRAFT_CREATED",
        entity_type="COMMUNICATION_DRAFT",
        entity_id=str(item.id),
        correlation_id=correlation_id,
    )
    return item


def edit_communication(
    session: Session,
    *,
    draft_id: UUID,
    subject: str,
    body: str,
    principal: Principal,
    correlation_id: str | None,
) -> CommunicationDraft:
    require_permission(principal, "communication.manage")
    item = session.get(CommunicationDraft, draft_id)
    if not item:
        raise NotFoundError("The requested communication draft was not found")
    _application(session, item.application_id, principal)
    if item.status != "DRAFT":
        raise ConflictError("Only drafts may be edited", code="communication_transition")
    item.subject = subject
    item.body = body
    record_audit_event(
        session,
        actor=principal,
        action="COMMUNICATION_DRAFT_EDITED",
        entity_type="COMMUNICATION_DRAFT",
        entity_id=str(item.id),
        correlation_id=correlation_id,
    )
    return item


def approve_and_queue(
    session: Session, *, draft_id: UUID, principal: Principal, correlation_id: str | None
) -> CommunicationDraft:
    require_permission(principal, "communication.approve")
    item = session.get(CommunicationDraft, draft_id)
    if not item:
        raise NotFoundError("The requested communication draft was not found")
    _application(session, item.application_id, principal)
    if item.status != "DRAFT":
        raise ConflictError(
            "Only draft communications may be approved", code="communication_transition"
        )
    item.status = "QUEUED_SIMULATED"
    item.approved_by_user_id = principal.user.id
    create_outbox_event(
        session,
        event_type="SIMULATED_COMMUNICATION_DISPATCH",
        aggregate_type="COMMUNICATION_DRAFT",
        aggregate_id=str(item.id),
        aggregate_version=None,
        payload={
            "application_id": str(item.application_id),
            "title": "Simulated communication queued",
            "body": "No external provider is configured; this is not a sent email or SMS.",
            "recipient_user_ids": [],
        },
        idempotency_key=f"communication:{item.id}:queue",
    )
    record_audit_event(
        session,
        actor=principal,
        action="COMMUNICATION_APPROVED_AND_QUEUED_SIMULATED",
        entity_type="COMMUNICATION_DRAFT",
        entity_id=str(item.id),
        correlation_id=correlation_id,
        after_summary={"real_delivery": False},
    )
    return item
