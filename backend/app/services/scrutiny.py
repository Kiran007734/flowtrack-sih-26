from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models import (
    Deficiency,
    DeficiencyResponse,
    Document,
    ReviewerAssignment,
    ScrutinyFinding,
    ScrutinyReview,
    User,
)
from app.permissions.access import Principal, require_institution_access, require_permission
from app.services.applications import execute_transition, get_application
from app.services.audit import record_audit_event
from app.services.outbox import create_outbox_event


def require_active_assignment(
    session: Session, *, application_id: UUID, principal: Principal
) -> ReviewerAssignment:
    now = datetime.now(UTC)
    assignment = session.scalar(
        select(ReviewerAssignment).where(
            ReviewerAssignment.application_id == application_id,
            ReviewerAssignment.reviewer_id == principal.user.id,
            ReviewerAssignment.responsibility == "SCRUTINY",
            ReviewerAssignment.status == "ACTIVE",
            ReviewerAssignment.valid_from <= now,
            (ReviewerAssignment.valid_until.is_(None) | (ReviewerAssignment.valid_until > now)),
        )
    )
    if assignment is None:
        from app.core.errors import AuthorizationError

        raise AuthorizationError("An active scrutiny assignment is required for this action")
    return assignment


def create_assignment(
    session: Session,
    *,
    application_id: UUID,
    reviewer_id: UUID,
    principal: Principal,
    valid_until: datetime | None,
    reason: str | None,
    correlation_id: str | None,
) -> ReviewerAssignment:
    application = get_application(session, application_id, principal)
    require_permission(principal, "scrutiny.assign")
    reviewer = session.get(User, reviewer_id)
    if reviewer is None or not reviewer.is_active:
        raise NotFoundError("The requested reviewer was not found")
    from app.permissions.access import build_principal

    reviewer_principal = build_principal(session, reviewer)
    require_institution_access(reviewer_principal, application.institution)
    if "scrutiny.review" not in reviewer_principal.permissions:
        raise ConflictError(
            "The reviewer is not eligible for synthetic scrutiny", code="ineligible_reviewer"
        )
    active = session.scalar(
        select(ReviewerAssignment).where(
            ReviewerAssignment.application_id == application.id,
            ReviewerAssignment.reviewer_id == reviewer.id,
            ReviewerAssignment.responsibility == "SCRUTINY",
            ReviewerAssignment.status == "ACTIVE",
        )
    )
    if active is not None:
        raise ConflictError(
            "This reviewer already has an active scrutiny assignment", code="duplicate_assignment"
        )
    assignment = ReviewerAssignment(
        application_id=application.id,
        reviewer_id=reviewer.id,
        assigned_by_user_id=principal.user.id,
        responsibility="SCRUTINY",
        status="ACTIVE",
        valid_from=datetime.now(UTC),
        valid_until=valid_until,
        reason=reason,
    )
    session.add(assignment)
    record_audit_event(
        session,
        actor=principal,
        action="REVIEWER_ASSIGNED",
        entity_type="REVIEWER_ASSIGNMENT",
        entity_id=str(assignment.id),
        correlation_id=correlation_id,
        after_summary={"application_id": str(application.id), "reviewer_id": str(reviewer.id)},
    )
    return assignment


def revoke_assignment(
    session: Session,
    *,
    assignment_id: UUID,
    principal: Principal,
    reason: str,
    correlation_id: str | None,
) -> ReviewerAssignment:
    assignment = session.get(ReviewerAssignment, assignment_id)
    if assignment is None:
        raise NotFoundError()
    application = get_application(session, assignment.application_id, principal)
    require_permission(principal, "scrutiny.assign")
    if assignment.status != "ACTIVE":
        raise ConflictError("Only active assignments can be revoked", code="assignment_not_active")
    assignment.status = "REVOKED"
    assignment.revoked_at = datetime.now(UTC)
    assignment.reason = reason
    record_audit_event(
        session,
        actor=principal,
        action="REVIEWER_ASSIGNMENT_REVOKED",
        entity_type="REVIEWER_ASSIGNMENT",
        entity_id=str(assignment.id),
        correlation_id=correlation_id,
        after_summary={"application_id": str(application.id), "reason": reason},
    )
    return assignment


def save_review(
    session: Session,
    *,
    application_id: UUID,
    principal: Principal,
    summary: str | None,
    findings: list[dict],
    correlation_id: str | None,
) -> ScrutinyReview:
    application = get_application(session, application_id, principal)
    require_permission(principal, "scrutiny.review")
    require_active_assignment(session, application_id=application.id, principal=principal)
    if application.current_stage_key != "scrutiny":
        raise ConflictError(
            "Scrutiny reviews are permitted only during the scrutiny stage",
            code="invalid_current_stage",
        )
    review = session.scalar(
        select(ScrutinyReview).where(
            ScrutinyReview.application_id == application.id,
            ScrutinyReview.reviewer_id == principal.user.id,
        )
    )
    if review is None:
        review = ScrutinyReview(
            application_id=application.id, reviewer_id=principal.user.id, summary=summary
        )
        session.add(review)
        session.flush()
    elif review.status != "DRAFT":
        raise ConflictError("Submitted reviews cannot be modified", code="review_locked")
    else:
        review.summary = summary
        for existing in session.scalars(
            select(ScrutinyFinding).where(ScrutinyFinding.review_id == review.id)
        ):
            session.delete(existing)
    for finding in findings:
        session.add(ScrutinyFinding(review_id=review.id, **finding))
    record_audit_event(
        session,
        actor=principal,
        action="SCRUTINY_REVIEW_SAVED",
        entity_type="SCRUTINY_REVIEW",
        entity_id=str(review.id),
        correlation_id=correlation_id,
    )
    return review


def list_deficiencies(
    session: Session, *, application_id: UUID, principal: Principal
) -> list[Deficiency]:
    application = get_application(session, application_id, principal)
    require_institution_access(principal, application.institution)
    return list(
        session.scalars(
            select(Deficiency)
            .where(Deficiency.application_id == application.id)
            .order_by(Deficiency.created_at)
        )
    )


def respond_to_deficiency(
    session: Session,
    *,
    deficiency_id: UUID,
    principal: Principal,
    response_text: str,
    document_id: UUID | None,
    correlation_id: str | None,
) -> Deficiency:
    deficiency = session.get(Deficiency, deficiency_id)
    if deficiency is None:
        raise NotFoundError()
    application = get_application(session, deficiency.application_id, principal)
    require_permission(principal, "application.write")
    if application.status != "RETURNED" or deficiency.status not in {"OPEN", "RESPONDED"}:
        raise ConflictError(
            "This deficiency cannot be answered in the current state",
            code="deficiency_not_actionable",
        )
    if document_id is not None:
        document = session.get(Document, document_id)
        if (
            document is None
            or document.application_id != application.id
            or document.status != "AVAILABLE"
        ):
            raise ConflictError(
                "Corrective evidence must be an available document for this application",
                code="invalid_deficiency_document",
            )
    session.add(
        DeficiencyResponse(
            deficiency_id=deficiency.id,
            responder_id=principal.user.id,
            response_text=response_text,
            document_id=document_id,
        )
    )
    deficiency.status = "RESPONDED"
    record_audit_event(
        session,
        actor=principal,
        action="DEFICIENCY_RESPONDED",
        entity_type="DEFICIENCY",
        entity_id=str(deficiency.id),
        correlation_id=correlation_id,
    )
    return deficiency


def return_for_correction(
    session: Session,
    *,
    application_id: UUID,
    principal: Principal,
    row_version: int,
    reason: str,
    deficiencies: list[dict],
    correlation_id: str | None,
):
    application = get_application(session, application_id, principal)
    require_permission(principal, "deficiency.manage")
    require_active_assignment(session, application_id=application.id, principal=principal)
    if application.current_stage_key != "scrutiny":
        raise ConflictError(
            "An application can be returned only from scrutiny", code="invalid_current_stage"
        )
    finding_ids = {
        item.id
        for item in session.scalars(
            select(ScrutinyFinding)
            .join(ScrutinyReview)
            .where(ScrutinyReview.application_id == application.id)
        )
    }
    created: list[Deficiency] = []
    for index, item in enumerate(deficiencies, start=1):
        finding_id = item.get("finding_id")
        if finding_id and finding_id not in finding_ids:
            raise ConflictError(
                "A deficiency finding must belong to this application", code="invalid_finding"
            )
        deficiency = Deficiency(
            application_id=application.id,
            finding_id=finding_id,
            identifier=f"SYN-DEF-{application.reference_number[-8:]}-{index:02d}-{uuid4().hex[:6].upper()}",
            description=item["description"],
            raised_by_user_id=principal.user.id,
        )
        session.add(deficiency)
        created.append(deficiency)
    transitioned = execute_transition(
        session,
        application_id=application.id,
        principal=principal,
        transition_key="return_for_correction",
        row_version=row_version,
        comment=reason,
        correlation_id=correlation_id,
    )
    create_outbox_event(
        session,
        event_type="APPLICATION_RETURNED",
        aggregate_type="APPLICATION",
        aggregate_id=str(application.id),
        aggregate_version=transitioned.row_version,
        payload={
            "application_id": str(application.id),
            "recipient_user_ids": [str(application.submitted_by_user_id)]
            if application.submitted_by_user_id
            else [],
            "title": "Application returned for correction",
            "body": reason,
        },
        idempotency_key=f"application:{application.id}:returned:v{transitioned.row_version}",
    )
    record_audit_event(
        session,
        actor=principal,
        action="APPLICATION_RETURNED_WITH_DEFICIENCIES",
        entity_type="APPLICATION",
        entity_id=str(application.id),
        correlation_id=correlation_id,
        after_summary={"deficiency_count": len(created), "reason": reason},
    )
    return transitioned, created
