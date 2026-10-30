from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models import (
    Application,
    DocumentVersion,
    EvcChecklistItem,
    EvcEvidenceLink,
    EvcReport,
    EvcVisit,
    EvcVisitPersonnel,
    User,
)
from app.permissions.access import (
    Principal,
    require_institution_access,
    require_permission,
    scoped_institution_ids,
)
from app.services.audit import record_audit_event
from app.services.documents import get_document
from app.services.outbox import create_outbox_event


def create_visit(
    session: Session,
    *,
    application_id: UUID,
    principal: Principal,
    data: dict,
    correlation_id: str | None,
) -> EvcVisit:
    app = session.get(Application, application_id)
    if app is None:
        raise NotFoundError()
    require_permission(principal, "evc.schedule")
    require_institution_access(principal, app.institution)
    if app.current_stage_key != "evc":
        raise ConflictError(
            "An EVC visit requires the configured EVC stage", code="invalid_current_stage"
        )
    if session.scalar(select(EvcVisit).where(EvcVisit.application_id == app.id)):
        raise ConflictError(
            "An EVC visit already exists for this application", code="duplicate_evc_visit"
        )
    if data["scheduled_start"].tzinfo is None or data["scheduled_start"] <= datetime.now(UTC):
        raise ConflictError(
            "Visit start must be a future timezone-aware timestamp", code="invalid_visit_time"
        )
    visit = EvcVisit(
        application_id=app.id,
        institution_id=app.institution_id,
        region_id=app.assigned_region_id,
        coordinator_id=principal.user.id,
        status="PROPOSED",
        **data,
    )
    session.add(visit)
    session.flush()
    record_audit_event(
        session,
        actor=principal,
        action="EVC_VISIT_PROPOSED",
        entity_type="EVC_VISIT",
        entity_id=str(visit.id),
        correlation_id=correlation_id,
        after_summary={"application_id": str(app.id)},
    )
    create_outbox_event(
        session,
        event_type="EVC_VISIT_PROPOSED",
        aggregate_type="EVC_VISIT",
        aggregate_id=str(visit.id),
        aggregate_version=1,
        payload={
            "application_id": str(app.id),
            "title": "Synthetic EVC visit proposed",
            "body": "A synthetic visit requires coordination.",
        },
        idempotency_key=f"evc:{visit.id}:proposed:v1",
    )
    return visit


def action_visit(
    session: Session,
    *,
    visit_id: UUID,
    principal: Principal,
    action: str,
    row_version: int,
    reason: str | None,
    correlation_id: str | None,
) -> EvcVisit:
    visit = session.get(EvcVisit, visit_id)
    if visit is None:
        raise NotFoundError()
    app = session.get(Application, visit.application_id)
    assert app is not None
    require_permission(principal, "evc.schedule")
    require_institution_access(principal, app.institution)
    if visit.row_version != row_version:
        raise ConflictError("The visit changed since it was opened", code="stale_row_version")
    states = {
        "confirm": ("PROPOSED", "CONFIRMED"),
        "start": ("CONFIRMED", "IN_PROGRESS"),
        "complete": ("IN_PROGRESS", "COMPLETED"),
        "cancel": ("PROPOSED", "CANCELLED"),
    }
    if action not in states or visit.status != states[action][0]:
        raise ConflictError(
            "This visit action is not permitted in the current state", code="invalid_visit_state"
        )
    if action == "cancel" and not reason:
        raise ConflictError("A cancellation reason is required", code="reason_required")
    visit.status = states[action][1]
    visit.row_version += 1
    record_audit_event(
        session,
        actor=principal,
        action=f"EVC_VISIT_{action.upper()}ED",
        entity_type="EVC_VISIT",
        entity_id=str(visit.id),
        correlation_id=correlation_id,
        after_summary={"reason": reason, "status": visit.status},
    )
    create_outbox_event(
        session,
        event_type=f"EVC_VISIT_{action.upper()}ED",
        aggregate_type="EVC_VISIT",
        aggregate_id=str(visit.id),
        aggregate_version=visit.row_version,
        payload={
            "application_id": str(app.id),
            "title": f"Synthetic EVC visit {visit.status.lower()}",
            "body": reason or "",
        },
        idempotency_key=f"evc:{visit.id}:{action}:v{visit.row_version}",
    )
    return visit


def _coordinator(session: Session, visit_id: UUID, principal: Principal) -> EvcVisit:
    visit = session.get(EvcVisit, visit_id)
    if visit is None:
        raise NotFoundError()
    app = session.get(Application, visit.application_id)
    assert app is not None
    require_permission(principal, "evc.schedule")
    require_institution_access(principal, app.institution)
    return visit


def add_personnel(
    session: Session,
    *,
    visit_id: UUID,
    user_id: UUID,
    role: str,
    principal: Principal,
    correlation_id: str | None,
) -> EvcVisitPersonnel:
    visit = _coordinator(session, visit_id, principal)
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise NotFoundError("Personnel user was not found")
    from app.permissions.access import build_principal

    candidate = build_principal(session, user)
    app = session.get(Application, visit.application_id)
    assert app is not None
    require_institution_access(candidate, app.institution)
    if "application.read" not in candidate.permissions:
        raise ConflictError(
            "Personnel are not eligible for this visit", code="ineligible_personnel"
        )
    item = EvcVisitPersonnel(visit_id=visit.id, user_id=user.id, role=role)
    session.add(item)
    record_audit_event(
        session,
        actor=principal,
        action="EVC_PERSONNEL_ASSIGNED",
        entity_type="EVC_VISIT",
        entity_id=str(visit.id),
        correlation_id=correlation_id,
        after_summary={"user_id": str(user.id)},
    )
    return item


def add_checklist(
    session: Session,
    *,
    visit_id: UUID,
    label: str,
    note: str | None,
    principal: Principal,
    correlation_id: str | None,
) -> EvcChecklistItem:
    visit = _coordinator(session, visit_id, principal)
    item = EvcChecklistItem(visit_id=visit.id, label=label, note=note)
    session.add(item)
    record_audit_event(
        session,
        actor=principal,
        action="EVC_CHECKLIST_ADDED",
        entity_type="EVC_VISIT",
        entity_id=str(visit.id),
        correlation_id=correlation_id,
    )
    return item


def submit_report(
    session: Session,
    *,
    visit_id: UUID,
    summary: str,
    principal: Principal,
    correlation_id: str | None,
) -> EvcReport:
    visit = _coordinator(session, visit_id, principal)
    if visit.status != "COMPLETED":
        raise ConflictError(
            "Complete the visit before submitting a report", code="invalid_visit_state"
        )
    report = EvcReport(
        visit_id=visit.id, author_id=principal.user.id, status="SUBMITTED", summary=summary
    )
    session.add(report)
    record_audit_event(
        session,
        actor=principal,
        action="EVC_REPORT_SUBMITTED",
        entity_type="EVC_REPORT",
        entity_id=str(report.id),
        correlation_id=correlation_id,
    )
    create_outbox_event(
        session,
        event_type="EVC_REPORT_SUBMITTED",
        aggregate_type="EVC_VISIT",
        aggregate_id=str(visit.id),
        aggregate_version=visit.row_version,
        payload={
            "application_id": str(visit.application_id),
            "title": "Synthetic EVC report submitted",
            "body": "Report awaits human review.",
        },
        idempotency_key=f"evc:{visit.id}:report:{report.id}",
    )
    return report


def complete_checklist(
    session: Session,
    *,
    item_id: UUID,
    principal: Principal,
    note: str | None,
    correlation_id: str | None,
) -> EvcChecklistItem:
    item = session.get(EvcChecklistItem, item_id)
    if item is None:
        raise NotFoundError()
    visit = _coordinator(session, item.visit_id, principal)
    if visit.status not in {"PROPOSED", "CONFIRMED", "IN_PROGRESS"}:
        raise ConflictError(
            "Checklist items cannot be completed for this visit state", code="invalid_visit_state"
        )
    item.status = "COMPLETED"
    item.note = note or item.note
    item.completed_by_user_id = principal.user.id
    item.completed_at = datetime.now(UTC)
    record_audit_event(
        session,
        actor=principal,
        action="EVC_CHECKLIST_COMPLETED",
        entity_type="EVC_CHECKLIST_ITEM",
        entity_id=str(item.id),
        correlation_id=correlation_id,
    )
    return item


def action_report(
    session: Session,
    *,
    report_id: UUID,
    action: str,
    principal: Principal,
    reason: str | None,
    correlation_id: str | None,
) -> EvcReport:
    report = session.get(EvcReport, report_id)
    if report is None:
        raise NotFoundError()
    visit = _coordinator(session, report.visit_id, principal)
    states = {
        "return": ("SUBMITTED", "RETURNED"),
        "resubmit": ("RETURNED", "SUBMITTED"),
        "accept": ("SUBMITTED", "ACCEPTED"),
        "close": ("ACCEPTED", "CLOSED"),
    }
    if action not in states or report.status != states[action][0]:
        raise ConflictError(
            "This report action is not permitted in the current state", code="invalid_report_state"
        )
    if action == "return" and not reason:
        raise ConflictError("A report return reason is required", code="reason_required")
    report.status = states[action][1]
    if action == "return":
        report.return_reason = reason
    record_audit_event(
        session,
        actor=principal,
        action=f"EVC_REPORT_{action.upper()}ED",
        entity_type="EVC_REPORT",
        entity_id=str(report.id),
        correlation_id=correlation_id,
        after_summary={"visit_id": str(visit.id), "reason": reason, "status": report.status},
    )
    create_outbox_event(
        session,
        event_type=f"EVC_REPORT_{action.upper()}ED",
        aggregate_type="EVC_VISIT",
        aggregate_id=str(visit.id),
        aggregate_version=visit.row_version,
        payload={
            "application_id": str(visit.application_id),
            "title": f"Synthetic EVC report {report.status.lower()}",
            "body": reason or "",
        },
        idempotency_key=f"evc-report:{report.id}:{action}",
    )
    return report


def link_evidence(
    session: Session,
    *,
    visit_id: UUID,
    document_id: UUID,
    document_version_id: UUID,
    purpose: str,
    comment: str | None,
    principal: Principal,
    correlation_id: str | None,
) -> EvcEvidenceLink:
    visit = _coordinator(session, visit_id, principal)
    document = get_document(session, document_id, principal)
    if document.application_id != visit.application_id:
        raise ConflictError(
            "Evidence document must belong to the visit application",
            code="invalid_evidence_document",
        )
    version = session.get(DocumentVersion, document_version_id)
    if version is None or version.document_id != document.id:
        raise ConflictError(
            "Document version does not belong to the supplied document",
            code="invalid_document_version",
        )
    link = EvcEvidenceLink(
        visit_id=visit.id,
        document_id=document.id,
        document_version_id=version.id,
        purpose=purpose,
        comment=comment,
    )
    session.add(link)
    session.flush()
    record_audit_event(
        session,
        actor=principal,
        action="EVC_EVIDENCE_LINKED",
        entity_type="EVC_EVIDENCE_LINK",
        entity_id=str(link.id),
        correlation_id=correlation_id,
        after_summary={"visit_id": str(visit.id), "document_version_id": str(version.id)},
    )
    create_outbox_event(
        session,
        event_type="EVC_EVIDENCE_LINKED",
        aggregate_type="EVC_VISIT",
        aggregate_id=str(visit.id),
        aggregate_version=visit.row_version,
        payload={"application_id": str(visit.application_id)},
        idempotency_key=f"evc-evidence:{link.id}:linked",
    )
    return link


def action_evidence(
    session: Session,
    *,
    link_id: UUID,
    action: str,
    reason: str | None,
    principal: Principal,
    correlation_id: str | None,
) -> EvcEvidenceLink:
    link = session.get(EvcEvidenceLink, link_id)
    if link is None:
        raise NotFoundError()
    visit = _coordinator(session, link.visit_id, principal)
    if link.status != "LINKED" or action not in {"verify", "reject"}:
        raise ConflictError("This evidence action is not permitted", code="invalid_evidence_state")
    if action == "reject" and not reason:
        raise ConflictError("An evidence rejection reason is required", code="reason_required")
    link.status = "VERIFIED" if action == "verify" else "REJECTED"
    link.comment = reason or link.comment
    link.verified_by_user_id = principal.user.id
    link.verified_at = datetime.now(UTC)
    event_action = "VERIFIED" if action == "verify" else "REJECTED"
    record_audit_event(
        session,
        actor=principal,
        action=f"EVC_EVIDENCE_{event_action}",
        entity_type="EVC_EVIDENCE_LINK",
        entity_id=str(link.id),
        correlation_id=correlation_id,
        after_summary={"visit_id": str(visit.id), "reason": reason},
    )
    create_outbox_event(
        session,
        event_type=f"EVC_EVIDENCE_{event_action}",
        aggregate_type="EVC_VISIT",
        aggregate_id=str(visit.id),
        aggregate_version=visit.row_version,
        payload={"application_id": str(visit.application_id)},
        idempotency_key=f"evc-evidence:{link.id}:{action}",
    )
    return link


def list_evidence(
    session: Session, *, visit_id: UUID, principal: Principal
) -> list[EvcEvidenceLink]:
    _coordinator(session, visit_id, principal)
    return list(
        session.scalars(
            select(EvcEvidenceLink)
            .where(EvcEvidenceLink.visit_id == visit_id)
            .order_by(EvcEvidenceLink.created_at, EvcEvidenceLink.id)
        )
    )


def get_evidence(session: Session, *, link_id: UUID, principal: Principal) -> EvcEvidenceLink:
    link = session.get(EvcEvidenceLink, link_id)
    if link is None:
        raise NotFoundError()
    _coordinator(session, link.visit_id, principal)
    return link


def list_visits(
    session: Session,
    *,
    principal: Principal,
    status: str | None = None,
    institution_id: UUID | None = None,
    region_id: UUID | None = None,
) -> list[EvcVisit]:
    require_permission(principal, "evc.schedule")
    query = select(EvcVisit).order_by(EvcVisit.scheduled_start.desc())
    institutions = scoped_institution_ids(session, principal)
    if institutions is not None:
        query = query.where(EvcVisit.institution_id.in_(institutions))
    if status:
        query = query.where(EvcVisit.status == status.upper())
    if institution_id:
        query = query.where(EvcVisit.institution_id == institution_id)
    if region_id:
        query = query.where(EvcVisit.region_id == region_id)
    return list(session.scalars(query))


def visit_detail(session: Session, *, visit_id: UUID, principal: Principal) -> dict:
    visit = _coordinator(session, visit_id, principal)
    personnel = list(
        session.scalars(select(EvcVisitPersonnel).where(EvcVisitPersonnel.visit_id == visit.id))
    )
    checklist = list(
        session.scalars(select(EvcChecklistItem).where(EvcChecklistItem.visit_id == visit.id))
    )
    reports = list(session.scalars(select(EvcReport).where(EvcReport.visit_id == visit.id)))
    evidence = list(
        session.scalars(select(EvcEvidenceLink).where(EvcEvidenceLink.visit_id == visit.id))
    )
    return {
        "visit": visit,
        "personnel": personnel,
        "checklist": checklist,
        "reports": reports,
        "evidence": evidence,
    }
