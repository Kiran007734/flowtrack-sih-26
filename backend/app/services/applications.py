from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AuthorizationError, ConflictError, NotFoundError, PrerequisiteError
from app.models import (
    Application,
    ApplicationStageHistory,
    ApplicationVersion,
    Institution,
    Role,
    RoleAssignment,
    User,
    WorkflowStage,
    WorkflowTemplate,
    WorkflowTemplateVersion,
    WorkflowTransition,
)
from app.permissions.access import (
    Principal,
    require_institution_access,
    require_permission,
    scoped_institution_ids,
)
from app.services.audit import record_audit_event
from app.services.outbox import create_outbox_event
from app.services.workflow import TransitionEvaluation, evaluate_transition


def _checksum(data: dict[str, Any]) -> str:
    return sha256(
        json.dumps(data, default=str, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _next_history_sequence(session: Session, application_id: UUID) -> int:
    current = session.scalar(
        select(func.max(ApplicationStageHistory.sequence)).where(
            ApplicationStageHistory.application_id == application_id
        )
    )
    return int(current or 0) + 1


def _application_summary(application: Application) -> dict[str, Any]:
    return {
        "reference_number": application.reference_number,
        "status": application.status,
        "current_stage_key": application.current_stage_key,
        "row_version": application.row_version,
    }


def get_application(
    session: Session, application_id: UUID, principal: Principal, *, lock: bool = False
) -> Application:
    statement = select(Application).where(Application.id == application_id)
    if lock:
        statement = statement.with_for_update()
    application = session.scalar(statement)
    if application is None:
        raise NotFoundError()
    require_permission(principal, "application.read")
    require_institution_access(principal, application.institution)
    return application


_APPLICATION_SORT_FIELDS = {
    "created_at": Application.created_at,
    "updated_at": Application.updated_at,
    "reference_number": Application.reference_number,
    "title": Application.title,
    "status": Application.status,
    "stage": Application.current_stage_key,
}


def _decode_application_cursor(cursor: str, *, sort_by: str, direction: str) -> tuple[object, UUID]:
    try:
        decoded = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        if decoded["sort_by"] != sort_by or decoded["direction"] != direction:
            raise ValueError
        value = decoded["value"]
        if sort_by in {"created_at", "updated_at"}:
            value = datetime.fromisoformat(value)
        return value, UUID(decoded["id"])
    except (KeyError, ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConflictError("The page cursor is invalid", code="invalid_cursor") from exc


def _encode_application_cursor(application: Application, *, sort_by: str, direction: str) -> str:
    value = getattr(application, sort_by if sort_by != "stage" else "current_stage_key")
    if isinstance(value, datetime):
        value = value.isoformat()
    raw = json.dumps(
        {"sort_by": sort_by, "direction": direction, "value": value, "id": str(application.id)},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(raw.encode()).decode()


def list_applications(
    session: Session,
    principal: Principal,
    *,
    limit: int = 50,
    cursor: str | None = None,
    search: str | None = None,
    institution_id: UUID | None = None,
    status: str | None = None,
    stage: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    sort_by: str = "created_at",
    sort_direction: str = "desc",
) -> tuple[list[Application], str | None]:
    require_permission(principal, "application.read")
    if sort_by not in _APPLICATION_SORT_FIELDS or sort_direction not in {"asc", "desc"}:
        raise ConflictError("Unsupported application sort", code="invalid_application_sort")
    if created_from and created_to and created_from > created_to:
        raise ConflictError(
            "The start date must not be after the end date", code="invalid_date_range"
        )
    sort_column = _APPLICATION_SORT_FIELDS[sort_by]
    descending = sort_direction == "desc"
    statement = select(Application)
    scope_ids = scoped_institution_ids(session, principal)
    if scope_ids is not None:
        if not scope_ids:
            return [], None
        statement = statement.where(Application.institution_id.in_(scope_ids))
    # An explicit institution filter is always intersected with the calculated scope.
    if institution_id:
        statement = statement.where(Application.institution_id == institution_id)
    if search and (term := search.strip()):
        like = f"%{term.lower()}%"
        statement = statement.where(
            or_(
                func.lower(Application.reference_number).like(like),
                func.lower(Application.title).like(like),
            )
        )
    if status:
        statement = statement.where(Application.status == status)
    if stage:
        statement = statement.where(Application.current_stage_key == stage)
    if created_from:
        statement = statement.where(Application.created_at >= created_from)
    if created_to:
        statement = statement.where(Application.created_at <= created_to)
    if cursor:
        cursor_value, cursor_id = _decode_application_cursor(
            cursor, sort_by=sort_by, direction=sort_direction
        )
        comparator = sort_column < cursor_value if descending else sort_column > cursor_value
        tie = Application.id < cursor_id if descending else Application.id > cursor_id
        statement = statement.where(or_(comparator, and_(sort_column == cursor_value, tie)))
    ordering = [
        sort_column.desc() if descending else sort_column.asc(),
        Application.id.desc() if descending else Application.id.asc(),
    ]
    records = list(session.scalars(statement.order_by(*ordering).limit(limit + 1)))
    has_more = len(records) > limit
    page = records[:limit]
    next_cursor = (
        _encode_application_cursor(page[-1], sort_by=sort_by, direction=sort_direction)
        if has_more and page
        else None
    )
    return page, next_cursor


def _published_template_version(session: Session, key: str) -> WorkflowTemplateVersion:
    version = session.scalar(
        select(WorkflowTemplateVersion)
        .join(WorkflowTemplate, WorkflowTemplate.id == WorkflowTemplateVersion.template_id)
        .where(
            WorkflowTemplate.key == key,
            WorkflowTemplate.is_active.is_(True),
            WorkflowTemplateVersion.is_published.is_(True),
        )
        .order_by(WorkflowTemplateVersion.version_number.desc())
        .limit(1)
    )
    if version is None:
        raise NotFoundError("No published synthetic workflow template was found")
    return version


def create_draft(
    session: Session,
    *,
    principal: Principal,
    institution_id: UUID,
    application_type: str,
    title: str,
    workflow_template_key: str,
    data: dict[str, Any],
    correlation_id: str | None,
) -> Application:
    require_permission(principal, "application.write")
    institution = session.get(Institution, institution_id)
    if institution is None or not institution.is_active:
        raise NotFoundError("The requested institution was not found")
    require_institution_access(principal, institution)
    template_version = _published_template_version(session, workflow_template_key)
    initial_stage = session.scalar(
        select(WorkflowStage).where(
            WorkflowStage.template_version_id == template_version.id,
            WorkflowStage.is_initial.is_(True),
        )
    )
    if initial_stage is None:
        raise ConflictError("The selected workflow has no initial stage", code="invalid_workflow")

    application = Application(
        institution_id=institution.id,
        assigned_region_id=institution.region_id,
        workflow_template_version_id=template_version.id,
        reference_number=f"DEMO-APP-{uuid4().hex[:12].upper()}",
        application_type=application_type.strip(),
        title=title.strip(),
        status="DRAFT",
        current_stage_key=initial_stage.key,
        current_version_number=1,
        row_version=1,
    )
    session.add(application)
    session.flush()
    version_data = dict(data)
    version_data.update(
        {"title": application.title, "application_type": application.application_type}
    )
    session.add(
        ApplicationVersion(
            application_id=application.id,
            version_number=1,
            data=version_data,
            checksum=_checksum(version_data),
        )
    )
    session.add(
        ApplicationStageHistory(
            application_id=application.id,
            sequence=1,
            transition_key="CREATE_DRAFT",
            from_stage_key=None,
            to_stage_key=initial_stage.key,
            actor_id=principal.user.id,
            facts={"workflow_template_version_id": str(template_version.id)},
            correlation_id=correlation_id,
        )
    )
    record_audit_event(
        session,
        actor=principal,
        action="APPLICATION_CREATED",
        entity_type="APPLICATION",
        entity_id=str(application.id),
        correlation_id=correlation_id,
        after_summary=_application_summary(application),
    )
    create_outbox_event(
        session,
        event_type="APPLICATION_DRAFT_CREATED",
        aggregate_type="APPLICATION",
        aggregate_id=str(application.id),
        aggregate_version=application.row_version,
        payload={"application_id": str(application.id)},
        idempotency_key=f"application:{application.id}:draft-created:v1",
    )
    return application


def latest_application_data(session: Session, application: Application) -> dict[str, Any]:
    version = session.scalar(
        select(ApplicationVersion)
        .where(ApplicationVersion.application_id == application.id)
        .order_by(ApplicationVersion.version_number.desc())
        .limit(1)
    )
    return dict(version.data) if version else {}


def update_draft(
    session: Session,
    *,
    application_id: UUID,
    principal: Principal,
    row_version: int,
    title: str | None,
    application_type: str | None,
    data: dict[str, Any] | None,
    correlation_id: str | None,
) -> Application:
    application = get_application(session, application_id, principal, lock=True)
    require_permission(principal, "application.write")
    if application.status != "DRAFT":
        raise ConflictError(
            "Only draft applications can be edited", code="application_not_editable"
        )
    if application.row_version != row_version:
        raise ConflictError("The application changed since it was opened", code="stale_row_version")
    before = _application_summary(application)
    latest = latest_application_data(session, application)
    if title is not None:
        application.title = title.strip()
    if application_type is not None:
        application.application_type = application_type.strip()
    if data is not None:
        latest.update(data)
    latest.update({"title": application.title, "application_type": application.application_type})
    application.current_version_number += 1
    application.row_version += 1
    session.add(
        ApplicationVersion(
            application_id=application.id,
            version_number=application.current_version_number,
            data=latest,
            checksum=_checksum(latest),
        )
    )
    record_audit_event(
        session,
        actor=principal,
        action="APPLICATION_DRAFT_UPDATED",
        entity_type="APPLICATION",
        entity_id=str(application.id),
        correlation_id=correlation_id,
        before_summary=before,
        after_summary=_application_summary(application),
    )
    create_outbox_event(
        session,
        event_type="APPLICATION_DRAFT_UPDATED",
        aggregate_type="APPLICATION",
        aggregate_id=str(application.id),
        aggregate_version=application.row_version,
        payload={"application_id": str(application.id)},
        idempotency_key=f"application:{application.id}:draft-updated:v{application.row_version}",
    )
    return application


def _notification_recipients(
    session: Session, application: Application, submitter_id: UUID
) -> list[str]:
    role_keys = {"REGIONAL_OFFICER", "REGIONAL_ADMINISTRATOR"}
    assignments = list(
        session.execute(
            select(RoleAssignment, Role, User)
            .join(Role, Role.id == RoleAssignment.role_id)
            .join(User, User.id == RoleAssignment.user_id)
            .where(
                RoleAssignment.is_active.is_(True),
                User.is_active.is_(True),
                Role.key.in_(role_keys),
            )
        ).all()
    )
    recipient_ids = {
        assignment.user_id
        for assignment, _role, _user in assignments
        if assignment.scope_type == "GLOBAL"
        or (
            assignment.scope_type == "REGION"
            and assignment.region_id == application.assigned_region_id
        )
    }
    # A submitter receives a durable in-app acknowledgement even if no regional user is seeded.
    recipient_ids.add(submitter_id)
    return [str(item) for item in sorted(recipient_ids, key=str)]


def _raise_for_evaluation(evaluation: TransitionEvaluation) -> None:
    if evaluation.reason_code in {"missing_permission", "role_not_authorized"}:
        raise AuthorizationError(evaluation.explanation)
    if evaluation.reason_code == "prerequisites_unmet":
        raise PrerequisiteError(evaluation.explanation, evaluation.missing_prerequisites)
    raise ConflictError(evaluation.explanation, code=evaluation.reason_code)


def authorize_transition(
    session: Session,
    *,
    application_id: UUID,
    principal: Principal,
    transition_key: str,
) -> Application:
    """Check current actor authorization without re-evaluating an old command's state.

    An idempotency replay can legitimately occur after the successful command has
    moved the application to a new stage. Scope, permission, and configured-role
    checks must therefore happen before replay, while prerequisite/current-stage
    validation remains part of the first execution in ``execute_transition``.
    """

    application = get_application(session, application_id, principal)
    transition = session.scalar(
        select(WorkflowTransition).where(
            WorkflowTransition.template_version_id == application.workflow_template_version_id,
            WorkflowTransition.key == transition_key,
        )
    )
    if transition is None:
        raise ConflictError(
            "The requested transition is not configured", code="transition_not_found"
        )
    require_permission(principal, transition.required_permission)
    if transition.authorized_role_keys and not (
        principal.role_keys.intersection(transition.authorized_role_keys)
    ):
        raise AuthorizationError("Your role is not authorized for this workflow transition")
    return application


def execute_transition(
    session: Session,
    *,
    application_id: UUID,
    principal: Principal,
    transition_key: str,
    row_version: int,
    comment: str | None,
    correlation_id: str | None,
) -> Application:
    application = get_application(session, application_id, principal, lock=True)
    if application.row_version != row_version:
        raise ConflictError("The application changed since it was opened", code="stale_row_version")
    evaluation = evaluate_transition(
        session, application=application, principal=principal, transition_key=transition_key
    )
    if not evaluation.allowed:
        _raise_for_evaluation(evaluation)
    before = _application_summary(application)
    application.current_stage_key = str(evaluation.to_stage_key)
    if transition_key in {"submit", "resubmit_after_correction"}:
        application.status = "SUBMITTED"
        application.submitted_at = datetime.now(UTC)
        application.submitted_by_user_id = principal.user.id
        current_data = latest_application_data(session, application)
        application.current_version_number += 1
        session.add(
            ApplicationVersion(
                application_id=application.id,
                version_number=application.current_version_number,
                data=current_data,
                checksum=_checksum(current_data),
                is_submission_snapshot=True,
                submitted_at=application.submitted_at,
                submitted_by_user_id=principal.user.id,
            )
        )
    elif application.current_stage_key == "returned":
        application.status = "RETURNED"
    elif application.current_stage_key == "completed":
        application.status = "ROUTE_COMPLETE"
    else:
        application.status = "IN_REVIEW"
    application.row_version += 1
    history = ApplicationStageHistory(
        application_id=application.id,
        sequence=_next_history_sequence(session, application.id),
        transition_key=transition_key,
        from_stage_key=before["current_stage_key"],
        to_stage_key=application.current_stage_key,
        actor_id=principal.user.id,
        comment=comment,
        facts={
            "workflow_template_version_id": str(application.workflow_template_version_id),
            "evaluation": evaluation.reason_code,
        },
        correlation_id=correlation_id,
    )
    session.add(history)
    action = (
        "APPLICATION_SUBMITTED" if transition_key == "submit" else "WORKFLOW_TRANSITION_EXECUTED"
    )
    record_audit_event(
        session,
        actor=principal,
        action=action,
        entity_type="APPLICATION",
        entity_id=str(application.id),
        correlation_id=correlation_id,
        before_summary=before,
        after_summary=_application_summary(application),
    )
    if transition_key == "submit":
        create_outbox_event(
            session,
            event_type="APPLICATION_SUBMITTED",
            aggregate_type="APPLICATION",
            aggregate_id=str(application.id),
            aggregate_version=application.row_version,
            payload={
                "application_id": str(application.id),
                "recipient_user_ids": _notification_recipients(
                    session, application, principal.user.id
                ),
                "title": "Application submitted",
                "body": (
                    f"Synthetic application {application.reference_number} was submitted "
                    "for workflow review."
                ),
            },
            idempotency_key=f"application:{application.id}:submitted:v{application.row_version}",
        )
    else:
        create_outbox_event(
            session,
            event_type="WORKFLOW_TRANSITIONED",
            aggregate_type="APPLICATION",
            aggregate_id=str(application.id),
            aggregate_version=application.row_version,
            payload={"application_id": str(application.id), "transition_key": transition_key},
            idempotency_key=f"application:{application.id}:transition:{transition_key}:v{application.row_version}",
        )
    return application


def get_stage_history(session: Session, application: Application) -> list[ApplicationStageHistory]:
    return list(
        session.scalars(
            select(ApplicationStageHistory)
            .where(ApplicationStageHistory.application_id == application.id)
            .order_by(ApplicationStageHistory.sequence)
        )
    )


def transition_options(
    session: Session, application: Application, principal: Principal
) -> list[TransitionEvaluation]:
    transitions = list(
        session.scalars(
            select(WorkflowTransition).where(
                WorkflowTransition.template_version_id == application.workflow_template_version_id
            )
        )
    )
    return [
        evaluate_transition(
            session, application=application, principal=principal, transition_key=t.key
        )
        for t in transitions
    ]
