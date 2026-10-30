# ruff: noqa: E501, E701, E702
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models import (
    Application,
    CommitteeMemberSubmission,
    CommitteeReview,
    CommitteeReviewMember,
    User,
)
from app.permissions.access import (
    Principal,
    build_principal,
    require_application_access,
    require_permission,
)
from app.services.audit import record_audit_event
from app.services.outbox import create_outbox_event


def _application(session: Session, application_id: UUID, principal: Principal) -> Application:
    item = session.get(Application, application_id)
    if not item:
        raise NotFoundError("The requested application was not found")
    require_application_access(principal, item)
    return item


def create_review(
    session: Session,
    *,
    application_id: UUID,
    stage_key: str,
    committee_type: str,
    principal: Principal,
    correlation_id: str | None,
) -> CommitteeReview:
    require_permission(principal, "committee.manage")
    application = _application(session, application_id, principal)
    if application.current_stage_key != stage_key:
        raise ConflictError(
            "Committee review stage does not match the current application stage",
            code="committee_stage_mismatch",
        )
    active = session.scalar(
        select(CommitteeReview).where(
            CommitteeReview.application_id == application.id,
            CommitteeReview.stage_key == stage_key,
            CommitteeReview.status == "OPEN",
        )
    )
    if active:
        return active
    item = CommitteeReview(
        id=uuid4(),
        application_id=application.id,
        workflow_template_version_id=application.workflow_template_version_id,
        stage_key=stage_key,
        committee_type=committee_type.upper(),
        status="OPEN",
        meeting_metadata={},
    )
    session.add(item)
    session.flush()
    record_audit_event(
        session,
        actor=principal,
        action="COMMITTEE_REVIEW_CREATED",
        entity_type="COMMITTEE_REVIEW",
        entity_id=str(item.id),
        correlation_id=correlation_id,
        after_summary={"application_id": str(application.id), "stage": stage_key},
    )
    return item


def assign_member(
    session: Session,
    *,
    review_id: UUID,
    user_id: UUID,
    principal: Principal,
    correlation_id: str | None,
) -> CommitteeReviewMember:
    require_permission(principal, "committee.manage")
    review = session.get(CommitteeReview, review_id)
    if not review:
        raise NotFoundError("The requested committee review was not found")
    application = _application(session, review.application_id, principal)
    if review.status != "OPEN":
        raise ConflictError(
            "Members can only be assigned while the committee review is open",
            code="committee_assignment_blocked",
        )
    user = session.get(User, user_id)
    if not user or not user.is_active:
        raise NotFoundError("The requested active member was not found")
    # Assignment must not grant review authority. The member independently
    # needs the review permission and scope for this application's institution.
    member_principal = build_principal(session, user)
    require_permission(member_principal, "committee.review")
    require_application_access(member_principal, application)
    item = session.scalar(
        select(CommitteeReviewMember).where(
            CommitteeReviewMember.committee_review_id == review.id,
            CommitteeReviewMember.user_id == user_id,
        )
    )
    if item:
        return item
    item = CommitteeReviewMember(
        id=uuid4(),
        committee_review_id=review.id,
        user_id=user_id,
        assigned_by_user_id=principal.user.id,
        is_active=True,
    )
    session.add(item)
    record_audit_event(
        session,
        actor=principal,
        action="COMMITTEE_MEMBER_ASSIGNED",
        entity_type="COMMITTEE_REVIEW",
        entity_id=str(review.id),
        correlation_id=correlation_id,
        after_summary={"member_id": str(user_id)},
    )
    return item


def submit(
    session: Session,
    *,
    review_id: UUID,
    recommendation: str,
    findings: str,
    principal: Principal,
    correlation_id: str | None,
) -> CommitteeMemberSubmission:
    require_permission(principal, "committee.review")
    review = session.get(CommitteeReview, review_id)
    if not review:
        raise NotFoundError("The requested committee review was not found")
    _application(session, review.application_id, principal)
    assignment = session.scalar(
        select(CommitteeReviewMember).where(
            CommitteeReviewMember.committee_review_id == review.id,
            CommitteeReviewMember.user_id == principal.user.id,
            CommitteeReviewMember.is_active.is_(True),
        )
    )
    if not assignment or review.status != "OPEN":
        raise ConflictError(
            "You are not permitted to submit to this committee review",
            code="committee_submission_blocked",
        )
    if session.scalar(
        select(CommitteeMemberSubmission).where(
            CommitteeMemberSubmission.committee_review_id == review.id,
            CommitteeMemberSubmission.member_id == principal.user.id,
        )
    ):
        raise ConflictError("A member may submit only once", code="committee_submission_exists")
    item = CommitteeMemberSubmission(
        id=uuid4(),
        committee_review_id=review.id,
        member_id=principal.user.id,
        recommendation=recommendation,
        findings=findings,
        submitted_at=datetime.now(UTC),
    )
    session.add(item)
    record_audit_event(
        session,
        actor=principal,
        action="COMMITTEE_MEMBER_SUBMITTED",
        entity_type="COMMITTEE_REVIEW",
        entity_id=str(review.id),
        correlation_id=correlation_id,
        after_summary={"recommendation": recommendation},
    )
    return item


def finalize(
    session: Session,
    *,
    review_id: UUID,
    outcome: str,
    reason: str,
    principal: Principal,
    correlation_id: str | None,
) -> CommitteeReview:
    require_permission(principal, "committee.finalize")
    review = session.get(CommitteeReview, review_id, with_for_update=True)
    if not review:
        raise NotFoundError("The requested committee review was not found")
    _application(session, review.application_id, principal)
    if review.status != "OPEN":
        raise ConflictError(
            "This committee review is already finalized", code="committee_finalized"
        )
    if not session.scalar(
        select(CommitteeMemberSubmission).where(
            CommitteeMemberSubmission.committee_review_id == review.id
        )
    ):
        raise ConflictError(
            "At least one member submission is required", code="committee_no_submissions"
        )
    review.status = "FINALIZED"
    review.outcome = outcome
    review.outcome_reason = reason
    review.finalized_by_user_id = principal.user.id
    review.finalized_at = datetime.now(UTC)
    record_audit_event(
        session,
        actor=principal,
        action="COMMITTEE_REVIEW_FINALIZED",
        entity_type="COMMITTEE_REVIEW",
        entity_id=str(review.id),
        correlation_id=correlation_id,
        after_summary={"outcome": outcome, "advisory_only": True},
    )
    create_outbox_event(
        session,
        event_type="COMMITTEE_REVIEW_FINALIZED",
        aggregate_type="COMMITTEE_REVIEW",
        aggregate_id=str(review.id),
        aggregate_version=None,
        payload={
            "application_id": str(review.application_id),
            "title": "Committee review finalized",
            "body": "An advisory committee outcome is ready for authorized workflow review.",
            "recipient_user_ids": [],
        },
        idempotency_key=f"committee:{review.id}:finalized",
    )
    return review
