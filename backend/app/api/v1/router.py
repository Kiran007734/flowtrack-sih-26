# ruff: noqa: E501, E701, E702
from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import CurrentPrincipal, DbSession, IdempotencyKey, get_bearer_token
from app.core.errors import AuthorizationError, ConflictError, NotFoundError
from app.models import (
    ApplicationDecision,
    AuditEvent,
    CatalogueRequirement,
    CommitteeMemberSubmission,
    CommitteeReview,
    CommitteeReviewMember,
    CommunicationDraft,
    ComplianceEvidence,
    GuidanceSourceVersion,
    Institution,
    JobExecution,
    Notification,
    OutboxEvent,
    Region,
    RequirementEvidenceMapping,
    ReviewerAssignment,
    Role,
    RoleAssignment,
    User,
)
from app.models import (
    DeficiencyResponse as DeficiencyResponseRecord,
)
from app.permissions.access import (
    require_institution_access,
    require_permission,
    scoped_institution_ids,
)
from app.schemas.applications import (
    ApplicationCreate,
    ApplicationDetailResponse,
    ApplicationListFilters,
    ApplicationResponse,
    ApplicationUpdate,
    StageHistoryResponse,
    TransitionEvaluationResponse,
    TransitionExecuteRequest,
)
from app.schemas.auth import (
    AccountActivationRequest,
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
    RegistrationDecisionRequest,
    RegistrationRejectionRequest,
    RegistrationRequest,
    RegistrationResponse,
    RoleGrantRequest,
    RoleGrantResponse,
    UserAdminResponse,
)
from app.schemas.catalogue import (
    GuidanceSourceCreate,
    GuidanceVersionCreate,
    LifecycleAction,
    MappingCreate,
    RequirementCreate,
)
from app.schemas.committee import (
    CommitteeCreate,
    CommitteeFinalize,
    CommitteeMemberCreate,
    CommitteeSubmissionCreate,
)
from app.schemas.common import AuditEventResponse, MessageResponse, PaginatedResponse
from app.schemas.compliance import (
    EvidenceSubmit,
    ObligationCreate,
    ReviewAction,
    ValidityAction,
    ValidityCreate,
)
from app.schemas.decisions import CommunicationCreate, CommunicationEdit, DecisionCreate
from app.schemas.documents import DocumentResponse, DocumentVersionResponse
from app.schemas.evc import (
    ChecklistAction,
    ChecklistRequest,
    EvidenceAction,
    EvidenceLinkRequest,
    EvidenceResponse,
    PersonnelRequest,
    ReportAction,
    ReportRequest,
    VisitAction,
    VisitCreate,
    VisitResponse,
)
from app.schemas.ingestion import ExtractionCorrection, ExtractionReview, IngestionStart
from app.schemas.institutions import InstitutionResponse
from app.schemas.notifications import NotificationResponse
from app.schemas.scrutiny import (
    AssignmentCreateRequest,
    AssignmentResponse,
    DeficiencyResponseModel,
    DeficiencyResponseRequest,
    ReturnRequest,
    ReviewDraftRequest,
    ReviewResponse,
)
from app.schemas.workflow_admin import WorkflowVersionCreate
from app.services.ai_scrutiny import assist_scrutiny
from app.services.applications import (
    authorize_transition,
    create_draft,
    execute_transition,
    get_application,
    get_stage_history,
    latest_application_data,
    list_applications,
    transition_options,
    update_draft,
)
from app.services.audit import record_audit_event
from app.services.auth import authenticate_local_user, register_local_user, revoke_current_session
from app.services.catalogue import (
    action_mapping,
    action_requirement,
    action_source_version,
    create_mapping,
    create_requirement,
    create_source,
    create_source_version,
    get_mapping,
    get_requirement,
    list_mappings,
    list_requirements,
    list_sources,
    source_detail,
)
from app.services.committee import assign_member, create_review
from app.services.committee import finalize as finalize_committee
from app.services.committee import submit as submit_committee
from app.services.compliance import (
    create_obligation,
    create_validity,
    list_obligations,
    list_validity,
    renew_validity,
    review_evidence,
    submit_evidence,
)
from app.services.dashboard import dashboard_summary
from app.services.decisions import (
    approve_and_queue,
    create_communication,
    edit_communication,
    record_decision,
)
from app.services.documents import (
    current_document_version,
    document_versions,
    get_document,
    private_document_path,
    upload_document,
    upload_document_version,
)
from app.services.evc import (
    action_evidence,
    action_report,
    action_visit,
    add_checklist,
    add_personnel,
    complete_checklist,
    create_visit,
    get_evidence,
    link_evidence,
    list_evidence,
    list_visits,
    submit_report,
    visit_detail,
)
from app.services.idempotency import record_response, replay_response
from app.services.ingestion import (
    correct_page,
    list_runs,
    process_ingestion,
    review_run,
    run_detail,
    start_ingestion,
)
from app.services.retrieval import index_version
from app.services.retrieval import search as search_guidance
from app.services.scrutiny import (
    create_assignment,
    list_deficiencies,
    respond_to_deficiency,
    return_for_correction,
    revoke_assignment,
    save_review,
)
from app.services.user_admin import (
    approve_registration,
    assign_role,
    get_user,
    list_users,
    reject_registration,
    revoke_role,
    set_activation,
)
from app.services.workflow_admin import create_draft as create_workflow_draft
from app.services.workflow_admin import list_templates
from app.services.workflow_admin import publish as publish_workflow

router = APIRouter(tags=["v1"])


@router.get("/workflow-templates", tags=["Workflow administration"])
def workflow_templates(db: DbSession, principal: CurrentPrincipal) -> list[dict[str, object]]:
    return list_templates(db, principal)


@router.post(
    "/workflow-templates/{template_id}/versions", status_code=201, tags=["Workflow administration"]
)
def create_workflow_version(
    template_id: UUID,
    payload: WorkflowVersionCreate,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    require_permission(principal, "workflow-template.manage")
    command = {"template_id": str(template_id), **payload.model_dump(mode="json")}
    if replay := _idempotent_command(
        db, principal, "workflow.version.create", idempotency_key, command
    ):
        return replay
    item = create_workflow_draft(
        db,
        template_id=template_id,
        data=payload.model_dump(),
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    response = {
        "id": str(item.id),
        "template_id": str(item.template_id),
        "version_number": item.version_number,
        "is_published": item.is_published,
    }
    record_response(
        db,
        actor_id=principal.user.id,
        operation="workflow.version.create",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=201,
    )
    db.commit()
    return response


@router.post("/workflow-versions/{version_id}/publish", tags=["Workflow administration"])
def publish_workflow_version(
    version_id: UUID,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    require_permission(principal, "workflow-template.manage")
    command = {"version_id": str(version_id)}
    if replay := _idempotent_command(
        db, principal, "workflow.version.publish", idempotency_key, command
    ):
        return replay
    item = publish_workflow(
        db, version_id=version_id, principal=principal, correlation_id=_correlation_id(request)
    )
    response = {
        "id": str(item.id),
        "version_number": item.version_number,
        "is_published": item.is_published,
    }
    record_response(
        db,
        actor_id=principal.user.id,
        operation="workflow.version.publish",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=200,
    )
    db.commit()
    return response


def _committee_response(item: object) -> dict[str, object]:
    return {
        "id": str(item.id),
        "application_id": str(item.application_id),
        "workflow_template_version_id": str(item.workflow_template_version_id),
        "stage_key": item.stage_key,
        "committee_type": item.committee_type,
        "status": item.status,
        "outcome": item.outcome,
        "outcome_reason": item.outcome_reason,
        "finalized_at": item.finalized_at.isoformat() if item.finalized_at else None,
    }


def _decision_response(item: object) -> dict[str, object]:
    return {
        "id": str(item.id),
        "application_id": str(item.application_id),
        "workflow_template_version_id": str(item.workflow_template_version_id),
        "workflow_stage_key": item.workflow_stage_key,
        "outcome": item.outcome,
        "rationale": item.rationale,
        "application_row_version": item.application_row_version,
        "decided_at": item.decided_at.isoformat(),
    }


def _communication_response(item: object) -> dict[str, object]:
    return {
        "id": str(item.id),
        "application_id": str(item.application_id),
        "decision_id": str(item.decision_id) if item.decision_id else None,
        "subject": item.subject,
        "body": item.body,
        "status": item.status,
        "dispatched_at": item.dispatched_at.isoformat() if item.dispatched_at else None,
    }


@router.get("/applications/{application_id}/decisions", tags=["Decisions"])
def application_decisions(
    application_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> list[dict[str, object]]:
    application = get_application(db, application_id, principal)
    return [
        _decision_response(item)
        for item in db.scalars(
            select(ApplicationDecision)
            .where(ApplicationDecision.application_id == application.id)
            .order_by(ApplicationDecision.decided_at.desc())
        )
    ]


@router.get("/applications/{application_id}/communications", tags=["Communications"])
def application_communications(
    application_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> list[dict[str, object]]:
    application = get_application(db, application_id, principal)
    return [
        _communication_response(item)
        for item in db.scalars(
            select(CommunicationDraft)
            .where(CommunicationDraft.application_id == application.id)
            .order_by(CommunicationDraft.created_at.desc())
        )
    ]


@router.get("/applications/{application_id}/committee-reviews", tags=["Committee reviews"])
def application_committee_reviews(
    application_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> list[dict[str, object]]:
    application = get_application(db, application_id, principal)
    return [
        _committee_response(item)
        for item in db.scalars(
            select(CommitteeReview)
            .where(CommitteeReview.application_id == application.id)
            .order_by(CommitteeReview.created_at.desc())
        )
    ]


@router.get("/committee-reviews/{review_id}", tags=["Committee reviews"])
def committee_review_detail(
    review_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> dict[str, object]:
    item = db.get(CommitteeReview, review_id)
    if item is None:
        raise NotFoundError("The requested committee review was not found")
    get_application(db, item.application_id, principal)
    return {
        **_committee_response(item),
        "members": [
            {"id": str(member.id), "user_id": str(member.user_id), "is_active": member.is_active}
            for member in db.scalars(
                select(CommitteeReviewMember).where(
                    CommitteeReviewMember.committee_review_id == item.id
                )
            )
        ],
        "submissions": [
            {
                "id": str(submission.id),
                "member_id": str(submission.member_id),
                "recommendation": submission.recommendation,
                "findings": submission.findings,
                "submitted_at": submission.submitted_at.isoformat(),
            }
            for submission in db.scalars(
                select(CommitteeMemberSubmission).where(
                    CommitteeMemberSubmission.committee_review_id == item.id
                )
            )
        ],
    }


@router.post("/applications/{application_id}/decisions", status_code=201, tags=["Decisions"])
def create_application_decision(
    application_id: UUID,
    payload: DecisionCreate,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    get_application(db, application_id, principal)
    require_permission(principal, "decision.record")
    command = {"application_id": str(application_id), **payload.model_dump(mode="json")}
    if replay := _idempotent_command(db, principal, "decision.create", idempotency_key, command):
        return replay
    item = record_decision(
        db,
        application_id=application_id,
        outcome=payload.outcome,
        rationale=payload.rationale,
        row_version=payload.row_version,
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    response = _decision_response(item)
    record_response(
        db,
        actor_id=principal.user.id,
        operation="decision.create",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=201,
    )
    db.commit()
    return response


@router.post(
    "/applications/{application_id}/communications", status_code=201, tags=["Communications"]
)
def create_application_communication(
    application_id: UUID,
    payload: CommunicationCreate,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    get_application(db, application_id, principal)
    require_permission(principal, "communication.manage")
    command = {"application_id": str(application_id), **payload.model_dump(mode="json")}
    if replay := _idempotent_command(
        db, principal, "communication.create", idempotency_key, command
    ):
        return replay
    item = create_communication(
        db,
        application_id=application_id,
        decision_id=payload.decision_id,
        subject=payload.subject,
        body=payload.body,
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    response = _communication_response(item)
    record_response(
        db,
        actor_id=principal.user.id,
        operation="communication.create",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=201,
    )
    db.commit()
    return response


@router.post("/communications/{draft_id}/approve-and-queue", tags=["Communications"])
def approve_communication(
    draft_id: UUID,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    draft = db.get(CommunicationDraft, draft_id)
    if draft is None:
        raise NotFoundError("The requested communication draft was not found")
    get_application(db, draft.application_id, principal)
    require_permission(principal, "communication.approve")
    command = {"draft_id": str(draft_id)}
    if replay := _idempotent_command(
        db, principal, "communication.approve", idempotency_key, command
    ):
        return replay
    item = approve_and_queue(
        db, draft_id=draft_id, principal=principal, correlation_id=_correlation_id(request)
    )
    db.flush()
    response = _communication_response(item)
    record_response(
        db,
        actor_id=principal.user.id,
        operation="communication.approve",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=200,
    )
    db.commit()
    return response


@router.put("/communications/{draft_id}", tags=["Communications"])
def update_communication(
    draft_id: UUID,
    payload: CommunicationEdit,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    draft = db.get(CommunicationDraft, draft_id)
    if draft is None:
        raise NotFoundError("The requested communication draft was not found")
    get_application(db, draft.application_id, principal)
    require_permission(principal, "communication.manage")
    command = {"draft_id": str(draft_id), **payload.model_dump(mode="json")}
    if replay := _idempotent_command(db, principal, "communication.edit", idempotency_key, command):
        return replay
    item = edit_communication(
        db,
        draft_id=draft_id,
        subject=payload.subject,
        body=payload.body,
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    response = _communication_response(item)
    record_response(
        db,
        actor_id=principal.user.id,
        operation="communication.edit",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=200,
    )
    db.commit()
    return response


@router.post(
    "/applications/{application_id}/committee-reviews", status_code=201, tags=["Committee reviews"]
)
def create_committee_review(
    application_id: UUID,
    payload: CommitteeCreate,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    get_application(db, application_id, principal)
    require_permission(principal, "committee.manage")
    command = {"application_id": str(application_id), **payload.model_dump(mode="json")}
    if replay := _idempotent_command(db, principal, "committee.create", idempotency_key, command):
        return replay
    item = create_review(
        db,
        application_id=application_id,
        stage_key=payload.stage_key,
        committee_type=payload.committee_type,
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    response = _committee_response(item)
    record_response(
        db,
        actor_id=principal.user.id,
        operation="committee.create",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=201,
    )
    db.commit()
    return response


@router.post("/committee-reviews/{review_id}/members", status_code=201, tags=["Committee reviews"])
def assign_committee_member(
    review_id: UUID,
    payload: CommitteeMemberCreate,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    review = db.get(CommitteeReview, review_id)
    if review is None:
        raise NotFoundError("The requested committee review was not found")
    get_application(db, review.application_id, principal)
    require_permission(principal, "committee.manage")
    command = {"review_id": str(review_id), **payload.model_dump(mode="json")}
    if replay := _idempotent_command(db, principal, "committee.assign", idempotency_key, command):
        return replay
    item = assign_member(
        db,
        review_id=review_id,
        user_id=payload.user_id,
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    response = {
        "id": str(item.id),
        "review_id": str(item.committee_review_id),
        "user_id": str(item.user_id),
    }
    record_response(
        db,
        actor_id=principal.user.id,
        operation="committee.assign",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=201,
    )
    db.commit()
    return response


@router.post(
    "/committee-reviews/{review_id}/submissions", status_code=201, tags=["Committee reviews"]
)
def submit_committee_member_review(
    review_id: UUID,
    payload: CommitteeSubmissionCreate,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    review = db.get(CommitteeReview, review_id)
    if review is None:
        raise NotFoundError("The requested committee review was not found")
    get_application(db, review.application_id, principal)
    require_permission(principal, "committee.review")
    command = {"review_id": str(review_id), **payload.model_dump(mode="json")}
    if replay := _idempotent_command(db, principal, "committee.submit", idempotency_key, command):
        return replay
    item = submit_committee(
        db,
        review_id=review_id,
        recommendation=payload.recommendation,
        findings=payload.findings,
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    response = {
        "id": str(item.id),
        "recommendation": item.recommendation,
        "submitted_at": item.submitted_at.isoformat(),
    }
    record_response(
        db,
        actor_id=principal.user.id,
        operation="committee.submit",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=201,
    )
    db.commit()
    return response


@router.post("/committee-reviews/{review_id}/finalize", tags=["Committee reviews"])
def finalize_committee_review(
    review_id: UUID,
    payload: CommitteeFinalize,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    review = db.get(CommitteeReview, review_id)
    if review is None:
        raise NotFoundError("The requested committee review was not found")
    get_application(db, review.application_id, principal)
    require_permission(principal, "committee.finalize")
    command = {"review_id": str(review_id), **payload.model_dump(mode="json")}
    if replay := _idempotent_command(db, principal, "committee.finalize", idempotency_key, command):
        return replay
    item = finalize_committee(
        db,
        review_id=review_id,
        outcome=payload.outcome,
        reason=payload.reason,
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    response = _committee_response(item)
    record_response(
        db,
        actor_id=principal.user.id,
        operation="committee.finalize",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=200,
    )
    db.commit()
    return response


def _guidance_version_response(item: GuidanceSourceVersion) -> dict[str, object]:
    return {
        "id": str(item.id),
        "source_id": str(item.source_id),
        "version_number": item.version_number,
        "version_label": item.version_label,
        "effective_date": item.effective_date.isoformat() if item.effective_date else None,
        "content_hash": item.content_hash,
        "upload_metadata": item.upload_metadata,
        "status": item.status,
        "verification_status": item.verification_status,
        "created_by_user_id": str(item.created_by_user_id),
        "reviewed_by_user_id": str(item.reviewed_by_user_id) if item.reviewed_by_user_id else None,
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
    }


def _requirement_response(item: CatalogueRequirement) -> dict[str, object]:
    return {
        "id": str(item.id),
        "stable_identifier": item.stable_identifier,
        "version_number": item.version_number,
        "source_version_id": str(item.source_version_id),
        "title": item.title,
        "description": item.description,
        "category": item.category,
        "module_key": item.module_key,
        "section_reference": item.section_reference,
        "applicability_conditions": item.applicability_conditions,
        "evidence_metadata": item.evidence_metadata,
        "severity": item.severity,
        "status": item.status,
        "supersedes_requirement_id": str(item.supersedes_requirement_id)
        if item.supersedes_requirement_id
        else None,
        "reviewed_by_user_id": str(item.reviewed_by_user_id) if item.reviewed_by_user_id else None,
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
    }


def _mapping_response(item: RequirementEvidenceMapping) -> dict[str, object]:
    return {
        "id": str(item.id),
        "requirement_id": str(item.requirement_id),
        "application_id": str(item.application_id),
        "document_id": str(item.document_id),
        "document_version_id": str(item.document_version_id),
        "evc_evidence_link_id": str(item.evc_evidence_link_id)
        if item.evc_evidence_link_id
        else None,
        "compliance_evidence_id": str(item.compliance_evidence_id)
        if item.compliance_evidence_id
        else None,
        "status": item.status,
        "explanation": item.explanation,
        "mapping_method": item.mapping_method,
        "created_by_user_id": str(item.created_by_user_id),
        "reviewed_by_user_id": str(item.reviewed_by_user_id) if item.reviewed_by_user_id else None,
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
        "review_reason": item.review_reason,
        "supersedes_mapping_id": str(item.supersedes_mapping_id)
        if item.supersedes_mapping_id
        else None,
    }


def _correlation_id(request: Request) -> str | None:
    return getattr(request.state, "correlation_id", None)


def _idempotent_command(
    db: DbSession, principal: CurrentPrincipal, operation: str, key: str, payload: dict[str, Any]
) -> dict[str, Any] | None:
    return replay_response(
        db, actor_id=principal.user.id, operation=operation, idempotency_key=key, payload=payload
    )


@router.get("/guidance-sources", tags=["Guidance catalogue"])
def guidance_sources(db: DbSession, principal: CurrentPrincipal) -> list[dict[str, object]]:
    return list_sources(db, principal=principal)


@router.get("/guidance-sources/{source_id}", tags=["Guidance catalogue"])
def guidance_source(
    source_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> dict[str, object]:
    return source_detail(db, source_id=source_id, principal=principal)


@router.post("/guidance-sources", status_code=201, tags=["Guidance catalogue"])
def create_guidance_source(
    payload: GuidanceSourceCreate,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    command = payload.model_dump(mode="json")
    replay = _idempotent_command(db, principal, "guidance.source.create", idempotency_key, command)
    if replay is not None:
        return replay
    item = create_source(
        db, data=payload.model_dump(), principal=principal, correlation_id=_correlation_id(request)
    )
    db.flush()
    version = db.scalar(
        select(GuidanceSourceVersion).where(
            GuidanceSourceVersion.source_id == item.id, GuidanceSourceVersion.version_number == 1
        )
    )
    assert version is not None
    response = {"id": str(item.id), "key": item.key, "version": _guidance_version_response(version)}
    record_response(
        db,
        actor_id=principal.user.id,
        operation="guidance.source.create",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=201,
    )
    db.commit()
    return response


@router.post("/guidance-sources/{source_id}/versions", status_code=201, tags=["Guidance catalogue"])
def add_guidance_version(
    source_id: UUID,
    payload: GuidanceVersionCreate,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    command = {"source_id": str(source_id), **payload.model_dump(mode="json")}
    replay = _idempotent_command(db, principal, "guidance.version.create", idempotency_key, command)
    if replay is not None:
        return replay
    item = create_source_version(
        db,
        source_id=source_id,
        data=payload.model_dump(),
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    response = _guidance_version_response(item)
    record_response(
        db,
        actor_id=principal.user.id,
        operation="guidance.version.create",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=201,
    )
    db.commit()
    if not payload.synchronous:
        # The run remains durably QUEUED if the broker is unavailable; no delivery is claimed.
        from app.tasks.jobs import process_guidance_ingestion

        try:
            process_guidance_ingestion.delay(str(item.id))
        except Exception:
            pass
    return response


@router.post(
    "/guidance-versions/{source_version_id}/ingestions",
    status_code=201,
    tags=["Guidance ingestion"],
)
def start_guidance_ingestion_early(
    source_version_id: UUID,
    payload: IngestionStart,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    command = {"source_version_id": str(source_version_id), **payload.model_dump(mode="json")}
    replay = _idempotent_command(
        db, principal, "guidance.ingestion.start", idempotency_key, command
    )
    if replay is not None:
        return replay
    item = start_ingestion(
        db,
        source_version_id=source_version_id,
        document_id=payload.document_id,
        document_version_id=payload.document_version_id,
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    if payload.synchronous:
        process_ingestion(
            db, run_id=item.id, principal=principal, correlation_id=_correlation_id(request)
        )
    db.flush()
    response = run_detail(db, run_id=item.id, principal=principal)
    record_response(
        db,
        actor_id=principal.user.id,
        operation="guidance.ingestion.start",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=201,
    )
    db.commit()
    return response


@router.post("/guidance-versions/{version_id}/{action}", tags=["Guidance catalogue"])
def guidance_version_action(
    version_id: UUID,
    action: str,
    payload: LifecycleAction,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    command = {"version_id": str(version_id), "action": action, **payload.model_dump(mode="json")}
    replay = _idempotent_command(db, principal, "guidance.version.action", idempotency_key, command)
    if replay is not None:
        return replay
    item = action_source_version(
        db,
        version_id=version_id,
        action=action,
        reason=payload.reason,
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    response = _guidance_version_response(item)
    record_response(
        db,
        actor_id=principal.user.id,
        operation="guidance.version.action",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=200,
    )
    db.commit()
    return response


@router.get("/guidance-versions/{source_version_id}/ingestions", tags=["Guidance ingestion"])
def guidance_ingestions(
    source_version_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> list[dict[str, object]]:
    return list_runs(db, source_version_id=source_version_id, principal=principal)


@router.post("/guidance-versions/{source_version_id}/index", tags=["Guidance retrieval"])
def index_guidance_version(
    source_version_id: UUID,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    command = {"source_version_id": str(source_version_id)}
    replay = _idempotent_command(db, principal, "guidance.index", idempotency_key, command)
    if replay is not None:
        return replay
    response = index_version(
        db,
        version_id=source_version_id,
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    record_response(
        db,
        actor_id=principal.user.id,
        operation="guidance.index",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=200,
    )
    db.commit()
    return response


@router.get("/guidance-search", tags=["Guidance retrieval"])
def guidance_search(
    question: str, db: DbSession, principal: CurrentPrincipal, limit: int = 10
) -> dict[str, object]:
    return {
        "mode": "LEXICAL_FALLBACK_NO_EMBEDDING_MODEL",
        "results": search_guidance(db, question=question, principal=principal, limit=limit),
    }


@router.get("/guidance-extraction-runs/{run_id}", tags=["Guidance ingestion"])
def guidance_extraction_run(
    run_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> dict[str, object]:
    return run_detail(db, run_id=run_id, principal=principal)


@router.post("/guidance-extraction-runs/{run_id}/review", tags=["Guidance ingestion"])
def review_guidance_extraction(
    run_id: UUID,
    payload: ExtractionReview,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    command = {"run_id": str(run_id), **payload.model_dump(mode="json")}
    replay = _idempotent_command(
        db, principal, "guidance.ingestion.review", idempotency_key, command
    )
    if replay is not None:
        return replay
    item = review_run(
        db,
        run_id=run_id,
        action=payload.action,
        reason=payload.reason,
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    response = run_detail(db, run_id=item.id, principal=principal)
    record_response(
        db,
        actor_id=principal.user.id,
        operation="guidance.ingestion.review",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=200,
    )
    db.commit()
    return response


@router.post("/guidance-extraction-pages/{page_id}/correction", tags=["Guidance ingestion"])
def correct_guidance_extraction(
    page_id: UUID,
    payload: ExtractionCorrection,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    command = {"page_id": str(page_id), **payload.model_dump(mode="json")}
    replay = _idempotent_command(
        db, principal, "guidance.ingestion.correct", idempotency_key, command
    )
    if replay is not None:
        return replay
    page = correct_page(
        db,
        page_id=page_id,
        corrected_text=payload.corrected_text,
        reason=payload.reason,
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    response = {
        "id": str(page.id),
        "corrected_at": page.corrected_at.isoformat() if page.corrected_at else None,
    }
    record_response(
        db,
        actor_id=principal.user.id,
        operation="guidance.ingestion.correct",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=200,
    )
    db.commit()
    return response


@router.get("/catalogue-requirements", tags=["Guidance catalogue"])
def catalogue_requirements(
    db: DbSession,
    principal: CurrentPrincipal,
    source_version_id: UUID | None = None,
    category: str | None = None,
    module_key: str | None = None,
    status: str | None = None,
) -> list[dict[str, object]]:
    return [
        _requirement_response(item)
        for item in list_requirements(
            db,
            principal=principal,
            source_version_id=source_version_id,
            category=category,
            module_key=module_key,
            status=status,
        )
    ]


@router.post("/catalogue-requirements", status_code=201, tags=["Guidance catalogue"])
def create_catalogue_requirement(
    payload: RequirementCreate,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    command = payload.model_dump(mode="json")
    replay = _idempotent_command(
        db, principal, "catalogue.requirement.create", idempotency_key, command
    )
    if replay is not None:
        return replay
    item = create_requirement(
        db, data=payload.model_dump(), principal=principal, correlation_id=_correlation_id(request)
    )
    db.flush()
    response = _requirement_response(item)
    record_response(
        db,
        actor_id=principal.user.id,
        operation="catalogue.requirement.create",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=201,
    )
    db.commit()
    return response


@router.get("/catalogue-requirements/{requirement_id}", tags=["Guidance catalogue"])
def catalogue_requirement(
    requirement_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> dict[str, object]:
    return _requirement_response(
        get_requirement(db, requirement_id=requirement_id, principal=principal)
    )


@router.post("/catalogue-requirements/{requirement_id}/{action}", tags=["Guidance catalogue"])
def catalogue_requirement_action(
    requirement_id: UUID,
    action: str,
    payload: LifecycleAction,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    command = {
        "requirement_id": str(requirement_id),
        "action": action,
        **payload.model_dump(mode="json"),
    }
    replay = _idempotent_command(
        db, principal, "catalogue.requirement.action", idempotency_key, command
    )
    if replay is not None:
        return replay
    item = action_requirement(
        db,
        requirement_id=requirement_id,
        action=action,
        reason=payload.reason,
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    response = _requirement_response(item)
    record_response(
        db,
        actor_id=principal.user.id,
        operation="catalogue.requirement.action",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=200,
    )
    db.commit()
    return response


@router.get("/requirement-evidence-mappings", tags=["Guidance catalogue"])
def requirement_evidence_mappings(
    db: DbSession,
    principal: CurrentPrincipal,
    application_id: UUID | None = None,
    requirement_id: UUID | None = None,
) -> list[dict[str, object]]:
    return [
        _mapping_response(item)
        for item in list_mappings(
            db, principal=principal, application_id=application_id, requirement_id=requirement_id
        )
    ]


@router.get("/requirement-evidence-mappings/{mapping_id}", tags=["Guidance catalogue"])
def requirement_evidence_mapping(
    mapping_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> dict[str, object]:
    return _mapping_response(get_mapping(db, mapping_id=mapping_id, principal=principal))


@router.get("/requirement-evidence-mappings/{mapping_id}/history", tags=["Guidance catalogue"])
def requirement_evidence_mapping_history(
    mapping_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> list[dict[str, object]]:
    get_mapping(db, mapping_id=mapping_id, principal=principal)
    events = db.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.entity_type == "REQUIREMENT_EVIDENCE_MAPPING",
            AuditEvent.entity_id == str(mapping_id),
        )
        .order_by(AuditEvent.created_at, AuditEvent.id)
    )
    return [
        {
            "action": event.action,
            "outcome": event.outcome,
            "reason": event.reason,
            "created_at": event.created_at.isoformat(),
        }
        for event in events
    ]


@router.post("/requirement-evidence-mappings", status_code=201, tags=["Guidance catalogue"])
def propose_requirement_evidence_mapping(
    payload: MappingCreate,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    command = payload.model_dump(mode="json")
    replay = _idempotent_command(
        db, principal, "catalogue.mapping.create", idempotency_key, command
    )
    if replay is not None:
        return replay
    item = create_mapping(
        db, data=payload.model_dump(), principal=principal, correlation_id=_correlation_id(request)
    )
    db.flush()
    response = _mapping_response(item)
    record_response(
        db,
        actor_id=principal.user.id,
        operation="catalogue.mapping.create",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=201,
    )
    db.commit()
    return response


@router.post("/requirement-evidence-mappings/{mapping_id}/{action}", tags=["Guidance catalogue"])
def requirement_evidence_mapping_action(
    mapping_id: UUID,
    action: str,
    payload: LifecycleAction,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    command = {"mapping_id": str(mapping_id), "action": action, **payload.model_dump(mode="json")}
    replay = _idempotent_command(
        db, principal, "catalogue.mapping.action", idempotency_key, command
    )
    if replay is not None:
        return replay
    item = action_mapping(
        db,
        mapping_id=mapping_id,
        action=action,
        reason=payload.reason,
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    response = _mapping_response(item)
    record_response(
        db,
        actor_id=principal.user.id,
        operation="catalogue.mapping.action",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=200,
    )
    db.commit()
    return response


@router.get("/compliance-obligations", tags=["Compliance"])
def compliance_obligations(db: DbSession, principal: CurrentPrincipal) -> list[dict[str, object]]:
    return [
        {
            "id": str(item.id),
            "application_id": str(item.application_id),
            "institution_id": str(item.institution_id),
            "title": item.title,
            "description": item.description,
            "due_at": item.due_at.isoformat() if item.due_at else None,
            "timezone": item.timezone,
            "required_evidence": item.required_evidence,
            "status": item.status,
            "row_version": item.row_version,
        }
        for item in list_obligations(db, principal=principal)
    ]


@router.post("/compliance-obligations", status_code=201, tags=["Compliance"])
def create_compliance_obligation(
    payload: ObligationCreate,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    command = payload.model_dump(mode="json")
    replay = _idempotent_command(
        db, principal, "compliance.obligation.create", idempotency_key, command
    )
    if replay is not None:
        return replay
    item = create_obligation(
        db, data=payload.model_dump(), principal=principal, correlation_id=_correlation_id(request)
    )
    db.flush()
    response = {"id": str(item.id), "status": item.status, "row_version": item.row_version}
    record_response(
        db,
        actor_id=principal.user.id,
        operation="compliance.obligation.create",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=201,
    )
    db.commit()
    return response


@router.post(
    "/compliance-obligations/{obligation_id}/evidence", status_code=201, tags=["Compliance"]
)
def submit_compliance_evidence(
    obligation_id: UUID,
    payload: EvidenceSubmit,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    command = {"obligation_id": str(obligation_id), **payload.model_dump(mode="json")}
    replay = _idempotent_command(
        db, principal, "compliance.evidence.submit", idempotency_key, command
    )
    if replay is not None:
        return replay
    item = submit_evidence(
        db,
        obligation_id=obligation_id,
        document_id=payload.document_id,
        document_version_id=payload.document_version_id,
        comment=payload.comment,
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    response = {
        "id": str(item.id),
        "status": item.status,
        "document_version_id": str(item.document_version_id),
    }
    record_response(
        db,
        actor_id=principal.user.id,
        operation="compliance.evidence.submit",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=201,
    )
    db.commit()
    return response


@router.post("/compliance-evidence/{evidence_id}/{action}", tags=["Compliance"])
def review_compliance_evidence(
    evidence_id: UUID,
    action: str,
    payload: ReviewAction,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    command = {"evidence_id": str(evidence_id), "action": action, **payload.model_dump(mode="json")}
    replay = _idempotent_command(
        db, principal, "compliance.evidence.review", idempotency_key, command
    )
    if replay is not None:
        return replay
    item = review_evidence(
        db,
        evidence_id=evidence_id,
        action=action,
        reason=payload.reason,
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    response = {"id": str(item.id), "status": item.status}
    record_response(
        db,
        actor_id=principal.user.id,
        operation="compliance.evidence.review",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=200,
    )
    db.commit()
    return response


@router.get("/validity-records", tags=["Compliance"])
def validity_records(db: DbSession, principal: CurrentPrincipal) -> list[dict[str, object]]:
    return [
        {
            "id": str(item.id),
            "document_id": str(item.document_id),
            "document_version_id": str(item.document_version_id),
            "category": item.category,
            "issuing_authority": item.issuing_authority,
            "issue_date": item.issue_date.isoformat() if item.issue_date else None,
            "expiry_date": item.expiry_date.isoformat() if item.expiry_date else None,
            "advance_notice_days": item.advance_notice_days,
            "verification_status": item.verification_status,
            "renewal_status": item.renewal_status,
        }
        for item in list_validity(db, principal=principal)
    ]


@router.post("/validity-records", status_code=201, tags=["Compliance"])
def create_validity_record(
    payload: ValidityCreate,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    command = payload.model_dump(mode="json")
    replay = _idempotent_command(db, principal, "validity.record.create", idempotency_key, command)
    if replay is not None:
        return replay
    item = create_validity(
        db, data=payload.model_dump(), principal=principal, correlation_id=_correlation_id(request)
    )
    db.flush()
    response = {
        "id": str(item.id),
        "verification_status": item.verification_status,
        "renewal_status": item.renewal_status,
    }
    record_response(
        db,
        actor_id=principal.user.id,
        operation="validity.record.create",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=201,
    )
    db.commit()
    return response


@router.post("/validity-records/{record_id}/renew", tags=["Compliance"])
def renew_validity_record(
    record_id: UUID,
    payload: ValidityAction,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    if payload.document_version_id is None:
        raise ConflictError(
            "A replacement document version is required", code="document_version_required"
        )
    command = {"record_id": str(record_id), **payload.model_dump(mode="json")}
    replay = _idempotent_command(db, principal, "validity.record.renew", idempotency_key, command)
    if replay is not None:
        return replay
    item = renew_validity(
        db,
        record_id=record_id,
        document_version_id=payload.document_version_id,
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    response = {
        "id": str(item.id),
        "renewal_status": item.renewal_status,
        "document_version_id": str(item.document_version_id),
    }
    record_response(
        db,
        actor_id=principal.user.id,
        operation="validity.record.renew",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=200,
    )
    db.commit()
    return response


@router.get("/dashboard/pendency", tags=["Dashboard"])
def pendency_dashboard(db: DbSession, principal: CurrentPrincipal) -> dict[str, object]:
    """Scoped, synthetic operational metrics. Ageing is days since the last stage-history event."""
    return dashboard_summary(db, principal=principal)


@router.get("/applications/{application_id}/ai-scrutiny-assist", tags=["AI assistance"])
def ai_scrutiny_assist(
    application_id: UUID, request: Request, db: DbSession, principal: CurrentPrincipal
) -> dict[str, object]:
    application = get_application(db, application_id, principal)
    result = assist_scrutiny(
        db, application=application, principal=principal, correlation_id=_correlation_id(request)
    )
    db.commit()
    return result


@router.get("/compliance-obligations/{obligation_id}", tags=["Compliance"])
def compliance_obligation_detail(
    obligation_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> dict[str, object]:
    from app.services.compliance import _obligation

    obligation = _obligation(db, obligation_id, principal, "compliance.manage")
    evidence = db.scalars(
        select(ComplianceEvidence)
        .where(ComplianceEvidence.obligation_id == obligation.id)
        .order_by(ComplianceEvidence.created_at.desc())
    )
    reminders = db.scalars(
        select(OutboxEvent)
        .where(
            OutboxEvent.aggregate_id == str(obligation.id),
            OutboxEvent.event_type == "COMPLIANCE_REMINDER",
        )
        .order_by(OutboxEvent.created_at.desc())
    )
    history = db.scalars(
        select(AuditEvent).where(
            AuditEvent.entity_id.in_(
                [str(obligation.id), *[str(item.id) for item in list(evidence)]]
            )
        )
    )
    evidence = db.scalars(
        select(ComplianceEvidence)
        .where(ComplianceEvidence.obligation_id == obligation.id)
        .order_by(ComplianceEvidence.created_at.desc())
    )
    return {
        "id": str(obligation.id),
        "title": obligation.title,
        "status": obligation.status,
        "due_at": obligation.due_at.isoformat() if obligation.due_at else None,
        "evidence": [
            {
                "id": str(item.id),
                "status": item.status,
                "document_id": str(item.document_id),
                "document_version_id": str(item.document_version_id),
                "comment": item.comment,
            }
            for item in evidence
        ],
        "history": [
            {
                "action": item.action,
                "created_at": item.created_at.isoformat(),
                "reason": item.reason,
            }
            for item in history
        ],
        "reminders": [
            {
                "kind": item.payload.get("reminder_kind"),
                "status": item.status,
                "created_at": item.created_at.isoformat(),
                "attempt_count": item.attempt_count,
            }
            for item in reminders
        ],
    }


def _actor_response(principal: CurrentPrincipal) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=principal.user.id,
        email=principal.user.email,
        display_name=principal.user.display_name,
        is_active=principal.user.is_active,
        roles=sorted(principal.role_keys),
        permissions=sorted(principal.permissions),
    )


def _user_admin_response(db: DbSession, user: User) -> UserAdminResponse:
    grants = list(db.scalars(select(RoleAssignment).where(RoleAssignment.user_id == user.id)))
    roles = (
        {
            item.id: item
            for item in db.scalars(
                select(Role).where(Role.id.in_([grant.role_id for grant in grants]))
            )
        }
        if grants
        else {}
    )
    return UserAdminResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        roles=sorted(
            {
                roles[grant.role_id].key
                for grant in grants
                if grant.is_active and grant.role_id in roles
            }
        ),
        registration_status=user.registration_status,
        created_at=user.created_at.isoformat(),
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
        grants=[
            RoleGrantResponse(
                id=grant.id,
                role_key=roles[grant.role_id].key,
                role_name=roles[grant.role_id].name,
                scope_type=grant.scope_type,
                institution_id=grant.institution_id,
                region_id=grant.region_id,
                is_active=grant.is_active,
            )
            for grant in grants
            if grant.role_id in roles
        ],
    )


def _replayed_user_admin_response(
    db: DbSession,
    *,
    principal: CurrentPrincipal,
    operation: str,
    idempotency_key: str,
    payload: dict[str, Any],
) -> UserAdminResponse | None:
    replay = replay_response(
        db,
        actor_id=principal.user.id,
        operation=operation,
        idempotency_key=idempotency_key,
        payload=payload,
    )
    return UserAdminResponse.model_validate(replay) if replay is not None else None


def _record_user_admin_response(
    db: DbSession,
    *,
    principal: CurrentPrincipal,
    operation: str,
    idempotency_key: str,
    payload: dict[str, Any],
    response: UserAdminResponse,
) -> None:
    record_response(
        db,
        actor_id=principal.user.id,
        operation=operation,
        idempotency_key=idempotency_key,
        payload=payload,
        response_body=response.model_dump(mode="json"),
        response_status=200,
    )


@router.get("/users", response_model=list[UserAdminResponse], tags=["User administration"])
def users(
    db: DbSession, principal: CurrentPrincipal, status: str | None = None, query: str | None = None
) -> list[UserAdminResponse]:
    return [
        _user_admin_response(db, user)
        for user in list_users(db, principal=principal, status=status, query=query)
    ]


@router.get("/user-administration/scopes", tags=["User administration"])
def user_administration_scopes(
    db: DbSession, principal: CurrentPrincipal
) -> dict[str, list[dict[str, str]]]:
    list_users(db, principal=principal, status=None, query=None)
    institutions = list(
        db.scalars(
            select(Institution).where(Institution.is_active.is_(True)).order_by(Institution.name)
        )
    )
    regions = list(
        db.scalars(select(Region).where(Region.is_active.is_(True)).order_by(Region.name))
    )
    return {
        "institutions": [
            {"id": str(item.id), "name": item.name, "region_id": str(item.region_id)}
            for item in institutions
        ],
        "regions": [{"id": str(item.id), "name": item.name} for item in regions],
    }


@router.get("/users/{user_id}", response_model=UserAdminResponse, tags=["User administration"])
def user_detail(user_id: UUID, db: DbSession, principal: CurrentPrincipal) -> UserAdminResponse:
    return _user_admin_response(db, get_user(db, principal=principal, user_id=user_id))


@router.post(
    "/users/{user_id}/approve", response_model=UserAdminResponse, tags=["User administration"]
)
def approve_user(
    user_id: UUID,
    payload: RegistrationDecisionRequest,
    db: DbSession,
    principal: CurrentPrincipal,
    key: IdempotencyKey,
) -> UserAdminResponse:
    request_payload = {"user_id": str(user_id), **payload.model_dump(mode="json")}
    list_users(db, principal=principal, status=None, query=None)
    replay = _replayed_user_admin_response(
        db,
        principal=principal,
        operation="user.approve",
        idempotency_key=key,
        payload=request_payload,
    )
    if replay is not None:
        return replay
    user = approve_registration(
        db, principal=principal, user_id=user_id, grant=payload.model_dump()
    )
    response = _user_admin_response(db, user)
    _record_user_admin_response(
        db,
        principal=principal,
        operation="user.approve",
        idempotency_key=key,
        payload=request_payload,
        response=response,
    )
    db.commit()
    return response


@router.post(
    "/users/{user_id}/reject", response_model=UserAdminResponse, tags=["User administration"]
)
def reject_user(
    user_id: UUID,
    payload: RegistrationRejectionRequest,
    db: DbSession,
    principal: CurrentPrincipal,
    key: IdempotencyKey,
) -> UserAdminResponse:
    request_payload = {"user_id": str(user_id), **payload.model_dump(mode="json")}
    list_users(db, principal=principal, status=None, query=None)
    replay = _replayed_user_admin_response(
        db,
        principal=principal,
        operation="user.reject",
        idempotency_key=key,
        payload=request_payload,
    )
    if replay is not None:
        return replay
    user = reject_registration(db, principal=principal, user_id=user_id, reason=payload.reason)
    response = _user_admin_response(db, user)
    _record_user_admin_response(
        db,
        principal=principal,
        operation="user.reject",
        idempotency_key=key,
        payload=request_payload,
        response=response,
    )
    db.commit()
    return response


@router.post(
    "/users/{user_id}/activation", response_model=UserAdminResponse, tags=["User administration"]
)
def user_activation(
    user_id: UUID,
    payload: AccountActivationRequest,
    db: DbSession,
    principal: CurrentPrincipal,
    key: IdempotencyKey,
) -> UserAdminResponse:
    request_payload = {"user_id": str(user_id), **payload.model_dump(mode="json")}
    list_users(db, principal=principal, status=None, query=None)
    replay = _replayed_user_admin_response(
        db,
        principal=principal,
        operation="user.activation",
        idempotency_key=key,
        payload=request_payload,
    )
    if replay is not None:
        return replay
    user = set_activation(db, principal=principal, user_id=user_id, is_active=payload.is_active)
    response = _user_admin_response(db, user)
    _record_user_admin_response(
        db,
        principal=principal,
        operation="user.activation",
        idempotency_key=key,
        payload=request_payload,
        response=response,
    )
    db.commit()
    return response


@router.post(
    "/users/{user_id}/roles",
    response_model=RoleGrantResponse,
    status_code=201,
    tags=["User administration"],
)
def user_role_assign(
    user_id: UUID,
    payload: RoleGrantRequest,
    db: DbSession,
    principal: CurrentPrincipal,
    _key: IdempotencyKey,
) -> RoleGrantResponse:
    grant = assign_role(db, principal=principal, user_id=user_id, grant=payload.model_dump())
    db.commit()
    role = db.get(Role, grant.role_id)
    return RoleGrantResponse(
        id=grant.id,
        role_key=role.key,
        role_name=role.name,
        scope_type=grant.scope_type,
        institution_id=grant.institution_id,
        region_id=grant.region_id,
        is_active=grant.is_active,
    )


@router.delete(
    "/users/{user_id}/roles/{grant_id}",
    response_model=MessageResponse,
    tags=["User administration"],
)
def user_role_revoke(
    user_id: UUID, grant_id: UUID, db: DbSession, principal: CurrentPrincipal, _key: IdempotencyKey
) -> MessageResponse:
    revoke_role(db, principal=principal, user_id=user_id, grant_id=grant_id)
    db.commit()
    return MessageResponse(message="Role grant revoked")


def _application_response(application: Any) -> ApplicationResponse:
    return ApplicationResponse.model_validate(application)


def _document_response(db: DbSession, document: Any) -> DocumentResponse:
    versions = [
        DocumentVersionResponse.model_validate(version)
        for version in document_versions(db, document)
    ]
    return DocumentResponse(
        id=document.id,
        institution_id=document.institution_id,
        application_id=document.application_id,
        classification=document.classification,
        current_version_number=document.current_version_number,
        status=document.status,
        created_at=document.created_at,
        versions=versions,
    )


def _replayed_application_response(
    db: DbSession,
    *,
    principal: CurrentPrincipal,
    operation: str,
    idempotency_key: str,
    payload: dict[str, Any],
) -> ApplicationResponse | None:
    replay = replay_response(
        db,
        actor_id=principal.user.id,
        operation=operation,
        idempotency_key=idempotency_key,
        payload=payload,
    )
    return ApplicationResponse.model_validate(replay) if replay is not None else None


def _record_application_response(
    db: DbSession,
    *,
    principal: CurrentPrincipal,
    operation: str,
    idempotency_key: str,
    payload: dict[str, Any],
    response: ApplicationResponse,
    response_status: int = 200,
) -> None:
    record_response(
        db,
        actor_id=principal.user.id,
        operation=operation,
        idempotency_key=idempotency_key,
        payload=payload,
        response_body=response.model_dump(mode="json"),
        response_status=response_status,
    )


@router.post("/auth/login", response_model=LoginResponse, tags=["Authentication"])
def login(payload: LoginRequest, request: Request, db: DbSession) -> LoginResponse:
    ip_address = request.client.host if request.client else None
    try:
        token, _user, principal = authenticate_local_user(
            db, email=payload.email, password=payload.password, ip_address=ip_address
        )
        db.commit()
    except Exception:
        # A failed attempt is durable for throttling; the response remains generic.
        db.commit()
        raise
    return LoginResponse(access_token=token, user=_actor_response(principal))


@router.post(
    "/auth/register",
    response_model=RegistrationResponse,
    status_code=202,
    tags=["Authentication"],
)
def register(payload: RegistrationRequest, request: Request, db: DbSession) -> RegistrationResponse:
    """Accept a least-privilege account request for administrator approval."""

    ip_address = request.client.host if request.client else None
    try:
        register_local_user(
            db,
            display_name=payload.display_name,
            email=str(payload.email),
            password=payload.password,
            ip_address=ip_address,
        )
        db.commit()
    except Exception:
        # Duplicate and throttled requests record failed attempts deliberately.
        db.commit()
        raise
    return RegistrationResponse(
        status="PENDING_ADMINISTRATOR_APPROVAL",
        message="Your account request was received. An administrator must approve it before you can sign in.",
    )


@router.post("/auth/logout", response_model=MessageResponse, tags=["Authentication"])
def logout(
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    _idempotency_key: IdempotencyKey,
    token: str = Depends(get_bearer_token),
) -> MessageResponse:
    revoke_current_session(db, token, principal)
    db.commit()
    return MessageResponse(message="Signed out")


@router.get("/me", response_model=CurrentUserResponse, tags=["Authentication"])
def current_user(principal: CurrentPrincipal) -> CurrentUserResponse:
    return _actor_response(principal)


@router.get("/institutions", response_model=PaginatedResponse, tags=["Institutions"])
def institutions(db: DbSession, principal: CurrentPrincipal, limit: int = 50) -> PaginatedResponse:
    require_permission(principal, "application.read")
    statement = (
        select(Institution)
        .where(Institution.is_active.is_(True))
        .order_by(Institution.name)
        .limit(min(max(limit, 1), 100))
    )
    scope_ids = scoped_institution_ids(db, principal)
    if scope_ids is not None:
        if not scope_ids:
            return PaginatedResponse(items=[])
        statement = statement.where(Institution.id.in_(scope_ids))
    return PaginatedResponse(
        items=[InstitutionResponse.model_validate(item) for item in db.scalars(statement)]
    )


@router.get(
    "/institutions/{institution_id}", response_model=InstitutionResponse, tags=["Institutions"]
)
def institution(
    institution_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> InstitutionResponse:
    require_permission(principal, "application.read")
    item = db.get(Institution, institution_id)
    if item is None:
        raise NotFoundError("The requested institution was not found")
    from app.permissions.access import require_institution_access

    require_institution_access(principal, item)
    return InstitutionResponse.model_validate(item)


@router.get("/applications", response_model=PaginatedResponse, tags=["Applications"])
def applications(
    db: DbSession,
    principal: CurrentPrincipal,
    filters: ApplicationListFilters = Depends(),
    limit: int = 50,
    cursor: str | None = None,
) -> PaginatedResponse:
    records, next_cursor = list_applications(
        db, principal, limit=min(max(limit, 1), 100), cursor=cursor, **filters.model_dump()
    )
    return PaginatedResponse(
        items=[_application_response(record) for record in records], next_cursor=next_cursor
    )


@router.post(
    "/applications", response_model=ApplicationResponse, status_code=201, tags=["Applications"]
)
def create_application(
    payload: ApplicationCreate,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> ApplicationResponse:
    request_payload = payload.model_dump(mode="json")
    require_permission(principal, "application.write")
    institution = db.get(Institution, payload.institution_id)
    if institution is None:
        raise NotFoundError("The requested institution was not found")
    require_institution_access(principal, institution)
    if replay := _replayed_application_response(
        db,
        principal=principal,
        operation="applications.create",
        idempotency_key=idempotency_key,
        payload=request_payload,
    ):
        return replay
    application = create_draft(
        db,
        principal=principal,
        institution_id=payload.institution_id,
        application_type=payload.application_type,
        title=payload.title,
        workflow_template_key=payload.workflow_template_key,
        data=payload.data,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    db.refresh(application)
    response = _application_response(application)
    _record_application_response(
        db,
        principal=principal,
        operation="applications.create",
        idempotency_key=idempotency_key,
        payload=request_payload,
        response=response,
        response_status=201,
    )
    db.commit()
    return response


@router.get(
    "/applications/{application_id}",
    response_model=ApplicationDetailResponse,
    tags=["Applications"],
)
def application_detail(
    application_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> ApplicationDetailResponse:
    application = get_application(db, application_id, principal)
    return ApplicationDetailResponse(
        **_application_response(application).model_dump(),
        latest_data=latest_application_data(db, application),
    )


@router.patch(
    "/applications/{application_id}", response_model=ApplicationResponse, tags=["Applications"]
)
def update_application(
    application_id: UUID,
    payload: ApplicationUpdate,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> ApplicationResponse:
    request_payload = {"application_id": str(application_id), **payload.model_dump(mode="json")}
    get_application(db, application_id, principal)
    require_permission(principal, "application.write")
    if replay := _replayed_application_response(
        db,
        principal=principal,
        operation="applications.update",
        idempotency_key=idempotency_key,
        payload=request_payload,
    ):
        return replay
    application = update_draft(
        db,
        application_id=application_id,
        principal=principal,
        row_version=payload.row_version,
        title=payload.title,
        application_type=payload.application_type,
        data=payload.data,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    db.refresh(application)
    response = _application_response(application)
    _record_application_response(
        db,
        principal=principal,
        operation="applications.update",
        idempotency_key=idempotency_key,
        payload=request_payload,
        response=response,
    )
    db.commit()
    return response


@router.post(
    "/applications/{application_id}/submit",
    response_model=ApplicationResponse,
    tags=["Applications"],
)
def submit_application(
    application_id: UUID,
    payload: TransitionExecuteRequest,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> ApplicationResponse:
    request_payload = {"application_id": str(application_id), **payload.model_dump(mode="json")}
    authorize_transition(
        db, application_id=application_id, principal=principal, transition_key="submit"
    )
    if replay := _replayed_application_response(
        db,
        principal=principal,
        operation="applications.submit",
        idempotency_key=idempotency_key,
        payload=request_payload,
    ):
        return replay
    application = execute_transition(
        db,
        application_id=application_id,
        principal=principal,
        transition_key="submit",
        row_version=payload.row_version,
        comment=payload.comment,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    db.refresh(application)
    response = _application_response(application)
    _record_application_response(
        db,
        principal=principal,
        operation="applications.submit",
        idempotency_key=idempotency_key,
        payload=request_payload,
        response=response,
    )
    db.commit()
    return response


@router.get(
    "/applications/{application_id}/timeline",
    response_model=PaginatedResponse,
    tags=["Applications"],
)
def application_timeline(
    application_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> PaginatedResponse:
    application = get_application(db, application_id, principal)
    return PaginatedResponse(
        items=[
            StageHistoryResponse.model_validate(item) for item in get_stage_history(db, application)
        ]
    )


@router.get(
    "/applications/{application_id}/transition-options",
    response_model=PaginatedResponse,
    tags=["Workflow"],
)
def application_transition_options(
    application_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> PaginatedResponse:
    application = get_application(db, application_id, principal)
    return PaginatedResponse(
        items=[
            TransitionEvaluationResponse(**item.__dict__)
            for item in transition_options(db, application, principal)
        ]
    )


@router.post(
    "/applications/{application_id}/scrutiny-reviews",
    response_model=ReviewResponse,
    tags=["Scrutiny"],
)
def save_scrutiny_review(
    application_id: UUID,
    payload: ReviewDraftRequest,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> ReviewResponse:
    command = {"application_id": str(application_id), **payload.model_dump(mode="json")}
    replay = replay_response(
        db,
        actor_id=principal.user.id,
        operation="scrutiny.review.save",
        idempotency_key=idempotency_key,
        payload=command,
    )
    if replay is not None:
        return ReviewResponse.model_validate(replay)
    review = save_review(
        db,
        application_id=application_id,
        principal=principal,
        summary=payload.summary,
        findings=[item.model_dump() for item in payload.findings],
        correlation_id=_correlation_id(request),
    )
    db.flush()
    db.refresh(review)
    response = ReviewResponse.model_validate(review)
    record_response(
        db,
        actor_id=principal.user.id,
        operation="scrutiny.review.save",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response.model_dump(mode="json"),
        response_status=200,
    )
    db.commit()
    return response


@router.get(
    "/applications/{application_id}/deficiencies",
    response_model=PaginatedResponse,
    tags=["Scrutiny"],
)
def application_deficiencies(
    application_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> PaginatedResponse:
    return PaginatedResponse(
        items=[
            DeficiencyResponseModel(
                id=item.id,
                application_id=item.application_id,
                identifier=item.identifier,
                status=item.status,
                description=item.description,
                finding_id=item.finding_id,
                created_at=item.created_at,
                resolved_at=item.resolved_at,
                responses=[
                    {
                        "response_text": response.response_text,
                        "document_id": str(response.document_id) if response.document_id else None,
                        "created_at": response.created_at.isoformat(),
                    }
                    for response in db.scalars(
                        select(DeficiencyResponseRecord)
                        .where(DeficiencyResponseRecord.deficiency_id == item.id)
                        .order_by(DeficiencyResponseRecord.created_at)
                    )
                ],
            )
            for item in list_deficiencies(db, application_id=application_id, principal=principal)
        ]
    )


@router.get(
    "/applications/{application_id}/reviewer-assignments",
    response_model=PaginatedResponse,
    tags=["Scrutiny"],
)
def application_reviewer_assignments(
    application_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> PaginatedResponse:
    application = get_application(db, application_id, principal)
    if "scrutiny.assign" not in principal.permissions and not any(
        item.reviewer_id == principal.user.id
        for item in db.scalars(
            select(ReviewerAssignment).where(ReviewerAssignment.application_id == application.id)
        )
    ):
        from app.core.errors import AuthorizationError

        raise AuthorizationError("Reviewer assignment history is restricted")
    assignments = db.scalars(
        select(ReviewerAssignment)
        .where(ReviewerAssignment.application_id == application.id)
        .order_by(ReviewerAssignment.created_at.desc())
    )
    return PaginatedResponse(
        items=[AssignmentResponse.model_validate(item) for item in assignments]
    )


@router.post(
    "/applications/{application_id}/reviewer-assignments",
    response_model=AssignmentResponse,
    status_code=201,
    tags=["Scrutiny"],
)
def assign_reviewer(
    application_id: UUID,
    payload: AssignmentCreateRequest,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> AssignmentResponse:
    command = {"application_id": str(application_id), **payload.model_dump(mode="json")}
    replay = replay_response(
        db,
        actor_id=principal.user.id,
        operation="reviewer_assignment.create",
        idempotency_key=idempotency_key,
        payload=command,
    )
    if replay is not None:
        return AssignmentResponse.model_validate(replay)
    assignment = create_assignment(
        db,
        application_id=application_id,
        reviewer_id=payload.reviewer_id,
        principal=principal,
        valid_until=payload.valid_until,
        reason=payload.reason,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    db.refresh(assignment)
    response = AssignmentResponse.model_validate(assignment)
    record_response(
        db,
        actor_id=principal.user.id,
        operation="reviewer_assignment.create",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response.model_dump(mode="json"),
        response_status=201,
    )
    db.commit()
    return response


@router.post(
    "/reviewer-assignments/{assignment_id}/revoke",
    response_model=AssignmentResponse,
    tags=["Scrutiny"],
)
def revoke_reviewer_assignment(
    assignment_id: UUID,
    payload: MessageResponse,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> AssignmentResponse:
    if len(payload.message.strip()) < 2:
        from app.core.errors import ConflictError

        raise ConflictError("A revocation reason is required", code="reason_required")
    command = {"assignment_id": str(assignment_id), "reason": payload.message}
    replay = replay_response(
        db,
        actor_id=principal.user.id,
        operation="reviewer_assignment.revoke",
        idempotency_key=idempotency_key,
        payload=command,
    )
    if replay is not None:
        return AssignmentResponse.model_validate(replay)
    assignment = revoke_assignment(
        db,
        assignment_id=assignment_id,
        principal=principal,
        reason=payload.message,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    db.refresh(assignment)
    response = AssignmentResponse.model_validate(assignment)
    record_response(
        db,
        actor_id=principal.user.id,
        operation="reviewer_assignment.revoke",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response.model_dump(mode="json"),
        response_status=200,
    )
    db.commit()
    return response


@router.post(
    "/applications/{application_id}/return-for-correction",
    response_model=ApplicationResponse,
    tags=["Scrutiny"],
)
def return_application_for_correction(
    application_id: UUID,
    payload: ReturnRequest,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> ApplicationResponse:
    command = {"application_id": str(application_id), **payload.model_dump(mode="json")}
    replay = replay_response(
        db,
        actor_id=principal.user.id,
        operation="applications.return_for_correction",
        idempotency_key=idempotency_key,
        payload=command,
    )
    if replay is not None:
        return ApplicationResponse.model_validate(replay)
    application, _items = return_for_correction(
        db,
        application_id=application_id,
        principal=principal,
        row_version=payload.row_version,
        reason=payload.reason,
        deficiencies=[item.model_dump() for item in payload.deficiencies],
        correlation_id=_correlation_id(request),
    )
    db.flush()
    db.refresh(application)
    response = _application_response(application)
    record_response(
        db,
        actor_id=principal.user.id,
        operation="applications.return_for_correction",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response.model_dump(mode="json"),
        response_status=200,
    )
    db.commit()
    return response


@router.post(
    "/deficiencies/{deficiency_id}/responses",
    response_model=DeficiencyResponseModel,
    tags=["Scrutiny"],
)
def respond_deficiency(
    deficiency_id: UUID,
    payload: DeficiencyResponseRequest,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> DeficiencyResponseModel:
    command = {"deficiency_id": str(deficiency_id), **payload.model_dump(mode="json")}
    replay = replay_response(
        db,
        actor_id=principal.user.id,
        operation="deficiency.respond",
        idempotency_key=idempotency_key,
        payload=command,
    )
    if replay is not None:
        return DeficiencyResponseModel.model_validate(replay)
    item = respond_to_deficiency(
        db,
        deficiency_id=deficiency_id,
        principal=principal,
        response_text=payload.response_text,
        document_id=payload.document_id,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    db.refresh(item)
    response = DeficiencyResponseModel(
        id=item.id,
        application_id=item.application_id,
        identifier=item.identifier,
        status=item.status,
        description=item.description,
        finding_id=item.finding_id,
        created_at=item.created_at,
        resolved_at=item.resolved_at,
    )
    record_response(
        db,
        actor_id=principal.user.id,
        operation="deficiency.respond",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response.model_dump(mode="json"),
        response_status=200,
    )
    db.commit()
    return response


@router.post(
    "/applications/{application_id}/transitions/{transition_key}",
    response_model=ApplicationResponse,
    tags=["Workflow"],
)
def transition_application(
    application_id: UUID,
    transition_key: str,
    payload: TransitionExecuteRequest,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> ApplicationResponse:
    request_payload = {
        "application_id": str(application_id),
        "transition_key": transition_key,
        **payload.model_dump(mode="json"),
    }
    authorize_transition(
        db, application_id=application_id, principal=principal, transition_key=transition_key
    )
    if replay := _replayed_application_response(
        db,
        principal=principal,
        operation="applications.transition",
        idempotency_key=idempotency_key,
        payload=request_payload,
    ):
        return replay
    application = execute_transition(
        db,
        application_id=application_id,
        principal=principal,
        transition_key=transition_key,
        row_version=payload.row_version,
        comment=payload.comment,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    db.refresh(application)
    response = _application_response(application)
    _record_application_response(
        db,
        principal=principal,
        operation="applications.transition",
        idempotency_key=idempotency_key,
        payload=request_payload,
        response=response,
    )
    db.commit()
    return response


async def _bounded_upload(file: UploadFile, maximum: int) -> bytes:
    data = await file.read(maximum + 1)
    if len(data) > maximum:
        from app.core.errors import DomainError

        raise DomainError(
            422, "document_too_large", "The uploaded document exceeds the configured size limit"
        )
    return data


@router.post(
    "/documents/uploads", response_model=DocumentResponse, status_code=201, tags=["Documents"]
)
async def create_document(
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
    application_id: UUID = Form(...),
    classification: str = Form("INTERNAL"),
    file: UploadFile = File(...),
) -> DocumentResponse:
    from app.core.config import get_settings
    from app.services.documents import private_storage

    settings = get_settings()
    content = await _bounded_upload(file, settings.max_upload_size_bytes)
    request_payload = {
        "application_id": str(application_id),
        "classification": classification,
        "original_filename": file.filename or "",
        "supplied_mime_type": file.content_type or "",
        "content_sha256": sha256(content).hexdigest(),
    }
    replay = replay_response(
        db,
        actor_id=principal.user.id,
        operation="documents.create",
        idempotency_key=idempotency_key,
        payload=request_payload,
    )
    if replay is not None:
        return DocumentResponse.model_validate(replay)
    document = upload_document(
        db,
        principal=principal,
        application_id=application_id,
        classification=classification,
        original_filename=file.filename,
        supplied_mime_type=file.content_type,
        content=content,
        correlation_id=_correlation_id(request),
        settings=settings,
    )
    storage_key = current_document_version(db, document).storage_key
    try:
        db.flush()
        db.refresh(document)
        response = _document_response(db, document)
        record_response(
            db,
            actor_id=principal.user.id,
            operation="documents.create",
            idempotency_key=idempotency_key,
            payload=request_payload,
            response_body=response.model_dump(mode="json"),
            response_status=201,
        )
        db.commit()
    except Exception:
        db.rollback()
        private_storage(settings).delete(storage_key)
        raise
    return response


@router.get("/documents/{document_id}", response_model=DocumentResponse, tags=["Documents"])
def document_detail(
    document_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> DocumentResponse:
    return _document_response(db, get_document(db, document_id, principal))


@router.get(
    "/documents/{document_id}/versions", response_model=PaginatedResponse, tags=["Documents"]
)
def versions(document_id: UUID, db: DbSession, principal: CurrentPrincipal) -> PaginatedResponse:
    document = get_document(db, document_id, principal)
    return PaginatedResponse(
        items=[
            DocumentVersionResponse.model_validate(item) for item in document_versions(db, document)
        ]
    )


@router.post(
    "/documents/{document_id}/versions", response_model=DocumentResponse, tags=["Documents"]
)
async def create_document_version(
    document_id: UUID,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
    file: UploadFile = File(...),
) -> DocumentResponse:
    from app.core.config import get_settings
    from app.services.documents import private_storage

    settings = get_settings()
    content = await _bounded_upload(file, settings.max_upload_size_bytes)
    request_payload = {
        "document_id": str(document_id),
        "original_filename": file.filename or "",
        "supplied_mime_type": file.content_type or "",
        "content_sha256": sha256(content).hexdigest(),
    }
    replay = replay_response(
        db,
        actor_id=principal.user.id,
        operation="documents.create_version",
        idempotency_key=idempotency_key,
        payload=request_payload,
    )
    if replay is not None:
        return DocumentResponse.model_validate(replay)
    document = upload_document_version(
        db,
        principal=principal,
        document_id=document_id,
        original_filename=file.filename,
        supplied_mime_type=file.content_type,
        content=content,
        correlation_id=_correlation_id(request),
        settings=settings,
    )
    storage_key = current_document_version(db, document).storage_key
    try:
        db.flush()
        db.refresh(document)
        response = _document_response(db, document)
        record_response(
            db,
            actor_id=principal.user.id,
            operation="documents.create_version",
            idempotency_key=idempotency_key,
            payload=request_payload,
            response_body=response.model_dump(mode="json"),
            response_status=200,
        )
        db.commit()
    except Exception:
        db.rollback()
        private_storage(settings).delete(storage_key)
        raise
    return response


@router.get("/documents/{document_id}/content", tags=["Documents"])
def download_document(
    document_id: UUID, request: Request, db: DbSession, principal: CurrentPrincipal
) -> FileResponse:
    version, path = private_document_path(
        db,
        document_id=document_id,
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    db.commit()
    return FileResponse(
        path=Path(path),
        media_type=version.mime_type,
        filename=version.original_filename,
        content_disposition_type="attachment",
    )


@router.get("/notifications", response_model=PaginatedResponse, tags=["Notifications"])
def notifications(db: DbSession, principal: CurrentPrincipal, limit: int = 50) -> PaginatedResponse:
    records = list(
        db.scalars(
            select(Notification)
            .where(Notification.user_id == principal.user.id)
            .order_by(Notification.created_at.desc())
            .limit(min(max(limit, 1), 100))
        )
    )
    return PaginatedResponse(items=[NotificationResponse.model_validate(item) for item in records])


@router.get(
    "/notifications/{notification_id}", response_model=NotificationResponse, tags=["Notifications"]
)
def notification(
    notification_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> NotificationResponse:
    record = db.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == principal.user.id
        )
    )
    if record is None:
        raise NotFoundError()
    return NotificationResponse.model_validate(record)


@router.post(
    "/notifications/{notification_id}/read",
    response_model=NotificationResponse,
    tags=["Notifications"],
)
def read_notification(
    notification_id: UUID,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> NotificationResponse:
    request_payload = {"notification_id": str(notification_id)}
    replay = replay_response(
        db,
        actor_id=principal.user.id,
        operation="notifications.mark_read",
        idempotency_key=idempotency_key,
        payload=request_payload,
    )
    if replay is not None:
        return NotificationResponse.model_validate(replay)
    record = db.scalar(
        select(Notification)
        .where(Notification.id == notification_id, Notification.user_id == principal.user.id)
        .with_for_update()
    )
    if record is None:
        raise NotFoundError()
    if record.status != "READ":
        record.status = "READ"
        record.read_at = datetime.now(UTC)
        record_audit_event(
            db,
            actor=principal,
            action="NOTIFICATION_MARKED_READ",
            entity_type="NOTIFICATION",
            entity_id=str(record.id),
            correlation_id=_correlation_id(request),
        )
    db.flush()
    db.refresh(record)
    response = NotificationResponse.model_validate(record)
    record_response(
        db,
        actor_id=principal.user.id,
        operation="notifications.mark_read",
        idempotency_key=idempotency_key,
        payload=request_payload,
        response_body=response.model_dump(mode="json"),
        response_status=200,
    )
    db.commit()
    return response


@router.get("/audit-events", response_model=PaginatedResponse, tags=["Audit"])
def audit_events(
    request: Request, db: DbSession, principal: CurrentPrincipal, limit: int = 50
) -> PaginatedResponse:
    require_permission(principal, "audit.read")
    if not any(grant.scope_type == "GLOBAL" for grant in principal.grants):
        raise AuthorizationError("Audit history requires an explicitly global audit grant")
    events = list(
        db.scalars(
            select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(min(max(limit, 1), 100))
        )
    )
    record_audit_event(
        db,
        actor=principal,
        action="AUDIT_HISTORY_VIEWED",
        entity_type="AUDIT_EVENT",
        entity_id="collection",
        correlation_id=_correlation_id(request),
    )
    db.commit()
    return PaginatedResponse(items=[AuditEventResponse.model_validate(item) for item in events])


@router.get("/diagnostics/jobs", response_model=PaginatedResponse, tags=["Operations"])
def job_diagnostics(
    db: DbSession, principal: CurrentPrincipal, limit: int = 50
) -> PaginatedResponse:
    require_permission(principal, "diagnostics.read")
    records = db.scalars(
        select(JobExecution).order_by(JobExecution.created_at.desc()).limit(min(max(limit, 1), 100))
    )
    return PaginatedResponse(
        items=[
            {
                "id": str(item.id),
                "task_name": item.task_name,
                "task_id": item.task_id,
                "status": item.status,
                "result_summary": item.result_summary,
                "completed_at": item.completed_at,
            }
            for item in records
        ]
    )


@router.post("/evc-visits", response_model=VisitResponse, status_code=201, tags=["EVC"])
def create_evc_visit(
    payload: VisitCreate,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> VisitResponse:
    command = payload.model_dump(mode="json")
    replay = replay_response(
        db,
        actor_id=principal.user.id,
        operation="evc.visit.create",
        idempotency_key=idempotency_key,
        payload=command,
    )
    if replay is not None:
        return VisitResponse.model_validate(replay)
    visit = create_visit(
        db,
        application_id=payload.application_id,
        principal=principal,
        data=payload.model_dump(exclude={"application_id"}),
        correlation_id=_correlation_id(request),
    )
    db.flush()
    db.refresh(visit)
    response = VisitResponse.model_validate(visit)
    record_response(
        db,
        actor_id=principal.user.id,
        operation="evc.visit.create",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response.model_dump(mode="json"),
        response_status=201,
    )
    db.commit()
    return response


@router.get("/evc-visits", response_model=list[VisitResponse], tags=["EVC"])
def list_evc_visits(
    db: DbSession,
    principal: CurrentPrincipal,
    status: str | None = None,
    institution_id: UUID | None = None,
    region_id: UUID | None = None,
) -> list[VisitResponse]:
    return [
        VisitResponse.model_validate(item)
        for item in list_visits(
            db,
            principal=principal,
            status=status,
            institution_id=institution_id,
            region_id=region_id,
        )
    ]


@router.get("/evc-visits/{visit_id}", tags=["EVC"])
def get_evc_visit(visit_id: UUID, db: DbSession, principal: CurrentPrincipal) -> dict[str, object]:
    detail = visit_detail(db, visit_id=visit_id, principal=principal)
    return {
        "visit": VisitResponse.model_validate(detail["visit"]).model_dump(mode="json"),
        "personnel": [
            {
                "id": str(item.id),
                "user_id": str(item.user_id),
                "role": item.role,
                "status": item.status,
            }
            for item in detail["personnel"]
        ],
        "checklist": [
            {
                "id": str(item.id),
                "label": item.label,
                "status": item.status,
                "note": item.note,
                "completed_at": item.completed_at.isoformat() if item.completed_at else None,
            }
            for item in detail["checklist"]
        ],
        "reports": [
            {
                "id": str(item.id),
                "status": item.status,
                "summary": item.summary,
                "return_reason": item.return_reason,
                "created_at": item.created_at.isoformat(),
            }
            for item in detail["reports"]
        ],
        "evidence": [
            EvidenceResponse.model_validate(item).model_dump(mode="json")
            for item in detail["evidence"]
        ],
    }


@router.get("/evc-visits/{visit_id}/reminders", tags=["EVC"])
def evc_visit_reminders(
    visit_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> list[dict[str, object]]:
    visit_detail(db, visit_id=visit_id, principal=principal)
    events = db.scalars(
        select(OutboxEvent)
        .where(OutboxEvent.aggregate_id == str(visit_id), OutboxEvent.event_type == "EVC_REMINDER")
        .order_by(OutboxEvent.created_at.desc())
    )
    return [
        {
            "id": str(item.id),
            "kind": item.payload.get("reminder_kind"),
            "status": item.status,
            "created_at": item.created_at.isoformat(),
            "attempt_count": item.attempt_count,
        }
        for item in events
    ]


@router.post("/evc-visits/{visit_id}/actions/{action}", response_model=VisitResponse, tags=["EVC"])
def act_evc_visit(
    visit_id: UUID,
    action: str,
    payload: VisitAction,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> VisitResponse:
    command = {"visit_id": str(visit_id), "action": action, **payload.model_dump(mode="json")}
    replay = replay_response(
        db,
        actor_id=principal.user.id,
        operation="evc.visit.action",
        idempotency_key=idempotency_key,
        payload=command,
    )
    if replay is not None:
        return VisitResponse.model_validate(replay)
    visit = action_visit(
        db,
        visit_id=visit_id,
        principal=principal,
        action=action,
        row_version=payload.row_version,
        reason=payload.reason,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    db.refresh(visit)
    response = VisitResponse.model_validate(visit)
    record_response(
        db,
        actor_id=principal.user.id,
        operation="evc.visit.action",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response.model_dump(mode="json"),
        response_status=200,
    )
    db.commit()
    return response


@router.post("/evc-visits/{visit_id}/personnel", tags=["EVC"])
def assign_evc_personnel(
    visit_id: UUID,
    payload: PersonnelRequest,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, str]:
    command = {"visit_id": str(visit_id), **payload.model_dump(mode="json")}
    replay = replay_response(
        db,
        actor_id=principal.user.id,
        operation="evc.personnel.add",
        idempotency_key=idempotency_key,
        payload=command,
    )
    if replay is not None:
        return replay
    item = add_personnel(
        db,
        visit_id=visit_id,
        user_id=payload.user_id,
        role=payload.role,
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    response = {"id": str(item.id), "status": item.status}
    record_response(
        db,
        actor_id=principal.user.id,
        operation="evc.personnel.add",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=201,
    )
    db.commit()
    return response


@router.post("/evc-visits/{visit_id}/checklist", tags=["EVC"])
def add_evc_checklist(
    visit_id: UUID,
    payload: ChecklistRequest,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, str]:
    command = {"visit_id": str(visit_id), **payload.model_dump(mode="json")}
    replay = replay_response(
        db,
        actor_id=principal.user.id,
        operation="evc.checklist.add",
        idempotency_key=idempotency_key,
        payload=command,
    )
    if replay is not None:
        return replay
    item = add_checklist(
        db,
        visit_id=visit_id,
        label=payload.label,
        note=payload.note,
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    response = {"id": str(item.id), "status": item.status}
    record_response(
        db,
        actor_id=principal.user.id,
        operation="evc.checklist.add",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=201,
    )
    db.commit()
    return response


@router.post("/evc-visits/{visit_id}/reports", tags=["EVC"])
def submit_evc_report(
    visit_id: UUID,
    payload: ReportRequest,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, str]:
    command = {"visit_id": str(visit_id), **payload.model_dump(mode="json")}
    replay = replay_response(
        db,
        actor_id=principal.user.id,
        operation="evc.report.submit",
        idempotency_key=idempotency_key,
        payload=command,
    )
    if replay is not None:
        return replay
    report = submit_report(
        db,
        visit_id=visit_id,
        summary=payload.summary,
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    response = {"id": str(report.id), "status": report.status}
    record_response(
        db,
        actor_id=principal.user.id,
        operation="evc.report.submit",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=201,
    )
    db.commit()
    return response


@router.get("/evc-visits/{visit_id}/evidence", response_model=list[EvidenceResponse], tags=["EVC"])
def list_evc_evidence(
    visit_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> list[EvidenceResponse]:
    return [
        EvidenceResponse.model_validate(item)
        for item in list_evidence(db, visit_id=visit_id, principal=principal)
    ]


@router.post(
    "/evc-visits/{visit_id}/evidence",
    response_model=EvidenceResponse,
    status_code=201,
    tags=["EVC"],
)
def create_evc_evidence(
    visit_id: UUID,
    payload: EvidenceLinkRequest,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> EvidenceResponse:
    command = {"visit_id": str(visit_id), **payload.model_dump(mode="json")}
    replay = replay_response(
        db,
        actor_id=principal.user.id,
        operation="evc.evidence.link",
        idempotency_key=idempotency_key,
        payload=command,
    )
    if replay is not None:
        return EvidenceResponse.model_validate(replay)
    evidence = link_evidence(
        db,
        visit_id=visit_id,
        document_id=payload.document_id,
        document_version_id=payload.document_version_id,
        purpose=payload.purpose,
        comment=payload.comment,
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    db.refresh(evidence)
    response = EvidenceResponse.model_validate(evidence)
    record_response(
        db,
        actor_id=principal.user.id,
        operation="evc.evidence.link",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response.model_dump(mode="json"),
        response_status=201,
    )
    db.commit()
    return response


@router.get("/evc-evidence/{link_id}", response_model=EvidenceResponse, tags=["EVC"])
def get_evc_evidence(link_id: UUID, db: DbSession, principal: CurrentPrincipal) -> EvidenceResponse:
    return EvidenceResponse.model_validate(get_evidence(db, link_id=link_id, principal=principal))


@router.get(
    "/evc-evidence/{link_id}/history", response_model=list[AuditEventResponse], tags=["EVC"]
)
def evc_evidence_history(
    link_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> list[AuditEventResponse]:
    get_evidence(db, link_id=link_id, principal=principal)
    events = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.entity_type == "EVC_EVIDENCE_LINK", AuditEvent.entity_id == str(link_id))
        .order_by(AuditEvent.created_at, AuditEvent.id)
    )
    return [AuditEventResponse.model_validate(item) for item in events]


@router.post("/evc-evidence/{link_id}/{action}", response_model=EvidenceResponse, tags=["EVC"])
def act_evc_evidence(
    link_id: UUID,
    action: str,
    payload: EvidenceAction,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> EvidenceResponse:
    command = {"link_id": str(link_id), "action": action, **payload.model_dump(mode="json")}
    replay = replay_response(
        db,
        actor_id=principal.user.id,
        operation="evc.evidence.action",
        idempotency_key=idempotency_key,
        payload=command,
    )
    if replay is not None:
        return EvidenceResponse.model_validate(replay)
    evidence = action_evidence(
        db,
        link_id=link_id,
        action=action,
        reason=payload.reason,
        principal=principal,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    db.refresh(evidence)
    response = EvidenceResponse.model_validate(evidence)
    record_response(
        db,
        actor_id=principal.user.id,
        operation="evc.evidence.action",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response.model_dump(mode="json"),
        response_status=200,
    )
    db.commit()
    return response


@router.post("/evc-checklist-items/{item_id}/complete", tags=["EVC"])
def complete_evc_checklist(
    item_id: UUID,
    payload: ChecklistAction,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, str]:
    command = {"item_id": str(item_id), **payload.model_dump(mode="json")}
    replay = replay_response(
        db,
        actor_id=principal.user.id,
        operation="evc.checklist.complete",
        idempotency_key=idempotency_key,
        payload=command,
    )
    if replay is not None:
        return replay
    item = complete_checklist(
        db,
        item_id=item_id,
        principal=principal,
        note=payload.note,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    response = {"id": str(item.id), "status": item.status}
    record_response(
        db,
        actor_id=principal.user.id,
        operation="evc.checklist.complete",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=200,
    )
    db.commit()
    return response


@router.post("/evc-reports/{report_id}/{action}", tags=["EVC"])
def act_evc_report(
    report_id: UUID,
    action: str,
    payload: ReportAction,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
) -> dict[str, str]:
    command = {"report_id": str(report_id), "action": action, **payload.model_dump(mode="json")}
    replay = replay_response(
        db,
        actor_id=principal.user.id,
        operation="evc.report.action",
        idempotency_key=idempotency_key,
        payload=command,
    )
    if replay is not None:
        return replay
    report = action_report(
        db,
        report_id=report_id,
        action=action,
        principal=principal,
        reason=payload.reason,
        correlation_id=_correlation_id(request),
    )
    db.flush()
    response = {"id": str(report.id), "status": report.status}
    record_response(
        db,
        actor_id=principal.user.id,
        operation="evc.report.action",
        idempotency_key=idempotency_key,
        payload=command,
        response_body=response,
        response_status=200,
    )
    db.commit()
    return response
