from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models import (
    Application,
    ComplianceEvidence,
    ComplianceObligation,
    DocumentVersion,
    ValidityRecord,
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


def _obligation(
    session: Session, obligation_id: UUID, principal: Principal, permission: str
) -> ComplianceObligation:
    obligation = session.get(ComplianceObligation, obligation_id)
    if obligation is None:
        raise NotFoundError()
    require_permission(principal, permission)
    app = session.get(Application, obligation.application_id)
    assert app is not None
    require_institution_access(principal, app.institution)
    return obligation


def create_obligation(
    session: Session, *, data: dict, principal: Principal, correlation_id: str | None
) -> ComplianceObligation:
    require_permission(principal, "compliance.manage")
    app = session.get(Application, data.pop("application_id"))
    if app is None:
        raise NotFoundError()
    require_institution_access(principal, app.institution)
    due_at = data.get("due_at")
    if due_at and due_at.tzinfo is None:
        raise ConflictError("Deadline must be timezone-aware", code="invalid_due_date")
    item = ComplianceObligation(
        application_id=app.id,
        institution_id=app.institution_id,
        created_by_user_id=principal.user.id,
        **data,
    )
    session.add(item)
    session.flush()
    record_audit_event(
        session,
        actor=principal,
        action="COMPLIANCE_OBLIGATION_CREATED",
        entity_type="COMPLIANCE_OBLIGATION",
        entity_id=str(item.id),
        correlation_id=correlation_id,
    )
    return item


def submit_evidence(
    session: Session,
    *,
    obligation_id: UUID,
    document_id: UUID,
    document_version_id: UUID,
    comment: str | None,
    principal: Principal,
    correlation_id: str | None,
) -> ComplianceEvidence:
    obligation = _obligation(session, obligation_id, principal, "compliance.manage")
    if obligation.status in {"CLOSED", "VERIFIED"}:
        raise ConflictError("This obligation is closed", code="invalid_obligation_state")
    document = get_document(session, document_id, principal)
    if document.application_id != obligation.application_id:
        raise ConflictError(
            "Evidence must belong to the obligation application", code="invalid_evidence_document"
        )
    version = session.get(DocumentVersion, document_version_id)
    if version is None or version.document_id != document.id:
        raise ConflictError(
            "Document version does not belong to the supplied document",
            code="invalid_document_version",
        )
    item = ComplianceEvidence(
        obligation_id=obligation.id,
        document_id=document.id,
        document_version_id=version.id,
        comment=comment,
        submitted_by_user_id=principal.user.id,
    )
    obligation.status = "SUBMITTED"
    obligation.row_version += 1
    session.add(item)
    session.flush()
    record_audit_event(
        session,
        actor=principal,
        action="COMPLIANCE_EVIDENCE_SUBMITTED",
        entity_type="COMPLIANCE_EVIDENCE",
        entity_id=str(item.id),
        correlation_id=correlation_id,
    )
    create_outbox_event(
        session,
        event_type="COMPLIANCE_EVIDENCE_SUBMITTED",
        aggregate_type="COMPLIANCE_OBLIGATION",
        aggregate_id=str(obligation.id),
        aggregate_version=obligation.row_version,
        payload={"application_id": str(obligation.application_id)},
        idempotency_key=f"compliance:{obligation.id}:evidence:{item.id}",
    )
    return item


def review_evidence(
    session: Session,
    *,
    evidence_id: UUID,
    action: str,
    reason: str | None,
    principal: Principal,
    correlation_id: str | None,
) -> ComplianceEvidence:
    item = session.get(ComplianceEvidence, evidence_id)
    if item is None:
        raise NotFoundError()
    obligation = _obligation(session, item.obligation_id, principal, "compliance.verify")
    if item.status != "SUBMITTED" or action not in {"verify", "return", "reject"}:
        raise ConflictError("Evidence action is not permitted", code="invalid_evidence_state")
    if action in {"return", "reject"} and not reason:
        raise ConflictError("A review reason is required", code="reason_required")
    item.status = {"verify": "VERIFIED", "return": "RETURNED", "reject": "REJECTED"}[action]
    item.comment = reason or item.comment
    item.reviewed_by_user_id = principal.user.id
    item.reviewed_at = datetime.now(UTC)
    obligation.status = (
        "VERIFIED" if action == "verify" else "RETURNED" if action == "return" else "CLOSED"
    )
    obligation.row_version += 1
    record_audit_event(
        session,
        actor=principal,
        action=f"COMPLIANCE_EVIDENCE_{item.status}",
        entity_type="COMPLIANCE_EVIDENCE",
        entity_id=str(item.id),
        correlation_id=correlation_id,
        after_summary={"reason": reason},
    )
    return item


def create_validity(
    session: Session, *, data: dict, principal: Principal, correlation_id: str | None
) -> ValidityRecord:
    require_permission(principal, "compliance.manage")
    document = get_document(session, data["document_id"], principal)
    version = session.get(DocumentVersion, data["document_version_id"])
    if version is None or version.document_id != document.id:
        raise ConflictError(
            "Document version does not belong to the supplied document",
            code="invalid_document_version",
        )
    if (
        data.get("issue_date")
        and data.get("expiry_date")
        and data["expiry_date"] <= data["issue_date"]
    ):
        raise ConflictError("Expiry must be after issue date", code="invalid_validity_dates")
    item = ValidityRecord(institution_id=document.institution_id, **data)
    session.add(item)
    session.flush()
    record_audit_event(
        session,
        actor=principal,
        action="VALIDITY_RECORD_CREATED",
        entity_type="VALIDITY_RECORD",
        entity_id=str(item.id),
        correlation_id=correlation_id,
    )
    return item


def list_obligations(session: Session, *, principal: Principal) -> list[ComplianceObligation]:
    require_permission(principal, "compliance.manage")
    query = select(ComplianceObligation).order_by(ComplianceObligation.due_at)
    ids = scoped_institution_ids(session, principal)
    if ids is not None:
        query = query.where(ComplianceObligation.institution_id.in_(ids))
    return list(session.scalars(query))


def list_validity(session: Session, *, principal: Principal) -> list[ValidityRecord]:
    require_permission(principal, "compliance.manage")
    query = select(ValidityRecord).order_by(ValidityRecord.expiry_date)
    ids = scoped_institution_ids(session, principal)
    if ids is not None:
        query = query.where(ValidityRecord.institution_id.in_(ids))
    return list(session.scalars(query))


def renew_validity(
    session: Session,
    *,
    record_id: UUID,
    document_version_id: UUID,
    principal: Principal,
    correlation_id: str | None,
) -> ValidityRecord:
    require_permission(principal, "compliance.manage")
    item = session.get(ValidityRecord, record_id)
    if item is None:
        raise NotFoundError()
    document = get_document(session, item.document_id, principal)
    version = session.get(DocumentVersion, document_version_id)
    if version is None or version.document_id != document.id:
        raise ConflictError(
            "Renewal version must belong to the registered document",
            code="invalid_document_version",
        )
    item.document_version_id = version.id
    item.renewal_status = "RENEWED"
    item.verification_status = "UNVERIFIED"
    record_audit_event(
        session,
        actor=principal,
        action="VALIDITY_RECORD_RENEWED",
        entity_type="VALIDITY_RECORD",
        entity_id=str(item.id),
        correlation_id=correlation_id,
        after_summary={"document_version_id": str(version.id)},
    )
    return item
