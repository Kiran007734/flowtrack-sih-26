# ruff: noqa: E501, E701, E702
from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models import (
    Permission,
    Role,
    WorkflowStage,
    WorkflowTemplate,
    WorkflowTemplateVersion,
    WorkflowTransition,
)
from app.permissions.access import Principal, require_permission
from app.services.audit import record_audit_event


def _validate(session: Session, data: dict) -> None:
    stages = data["stages"]
    keys = [stage["key"] for stage in stages]
    if len(keys) != len(set(keys)) or len({stage["ordinal"] for stage in stages}) != len(stages):
        raise ConflictError(
            "Stage keys and ordinals must be unique", code="invalid_workflow_configuration"
        )
    if sum(stage["is_initial"] for stage in stages) != 1:
        raise ConflictError(
            "Exactly one initial stage is required", code="invalid_workflow_configuration"
        )
    transition_keys = [transition.get("key") for transition in data["transitions"]]
    if len(transition_keys) != len(set(transition_keys)):
        raise ConflictError("Transition keys must be unique", code="invalid_workflow_configuration")
    permissions = set(session.scalars(select(Permission.code)))
    roles = set(session.scalars(select(Role.key).where(Role.is_active.is_(True))))
    edges: dict[str, set[str]] = {key: set() for key in keys}
    for stage in stages:
        prerequisites = stage.get("entry_prerequisites", [])
        if any(item not in keys for item in prerequisites):
            raise ConflictError(
                "Stage prerequisites must reference configured stages",
                code="invalid_workflow_configuration",
            )
    for transition in data["transitions"]:
        if transition["from_stage_key"] not in keys or transition["to_stage_key"] not in keys:
            raise ConflictError(
                "Transitions must reference configured stages",
                code="invalid_workflow_configuration",
            )
        if transition.get("required_permission") not in permissions:
            raise ConflictError(
                "Transitions must use registered permissions", code="invalid_workflow_configuration"
            )
        if unknown_roles := set(transition.get("authorized_role_keys", [])) - roles:
            raise ConflictError(
                f"Transitions reference unknown role keys: {', '.join(sorted(unknown_roles))}",
                code="invalid_workflow_configuration",
            )
        edges[transition["from_stage_key"]].add(transition["to_stage_key"])
    initial = next(stage["key"] for stage in stages if stage["is_initial"])
    reachable = {initial}
    pending = [initial]
    while pending:
        node = pending.pop()
        for target in edges[node]:
            if target not in reachable:
                reachable.add(target)
                pending.append(target)
    if set(keys) - reachable:
        raise ConflictError(
            "Every configured stage must be reachable from the initial stage",
            code="invalid_workflow_configuration",
        )


def list_templates(session: Session, principal: Principal) -> list[dict]:
    require_permission(principal, "workflow-template.manage")
    return [
        {
            "id": str(template.id),
            "key": template.key,
            "name": template.name,
            "versions": [
                {
                    "id": str(version.id),
                    "version_number": version.version_number,
                    "is_published": version.is_published,
                    "route_type": version.route_type,
                }
                for version in session.scalars(
                    select(WorkflowTemplateVersion)
                    .where(WorkflowTemplateVersion.template_id == template.id)
                    .order_by(WorkflowTemplateVersion.version_number.desc())
                )
            ],
        }
        for template in session.scalars(select(WorkflowTemplate).order_by(WorkflowTemplate.key))
    ]


def create_draft(
    session: Session,
    *,
    template_id: UUID,
    data: dict,
    principal: Principal,
    correlation_id: str | None,
) -> WorkflowTemplateVersion:
    require_permission(principal, "workflow-template.manage")
    _validate(session, data)
    template = session.get(WorkflowTemplate, template_id)
    if not template:
        raise NotFoundError("The requested workflow template was not found")
    number = (
        int(
            session.scalar(
                select(func.max(WorkflowTemplateVersion.version_number)).where(
                    WorkflowTemplateVersion.template_id == template.id
                )
            )
            or 0
        )
        + 1
    )
    version = WorkflowTemplateVersion(
        id=uuid4(),
        template_id=template.id,
        version_number=number,
        route_type=data["route_type"],
        verification_status="SYNTHETIC_CONFIGURATION",
        source_reference=data.get("source_reference"),
        is_published=False,
        configuration={"synthetic": True},
    )
    session.add(version)
    session.flush()
    for stage in data["stages"]:
        session.add(WorkflowStage(template_version_id=version.id, **stage))
    for transition in data["transitions"]:
        session.add(WorkflowTransition(template_version_id=version.id, **transition))
    record_audit_event(
        session,
        actor=principal,
        action="WORKFLOW_VERSION_DRAFT_CREATED",
        entity_type="WORKFLOW_TEMPLATE_VERSION",
        entity_id=str(version.id),
        correlation_id=correlation_id,
    )
    return version


def publish(
    session: Session, *, version_id: UUID, principal: Principal, correlation_id: str | None
) -> WorkflowTemplateVersion:
    require_permission(principal, "workflow-template.manage")
    version = session.get(WorkflowTemplateVersion, version_id)
    if not version:
        raise NotFoundError("The requested workflow version was not found")
    if version.is_published:
        raise ConflictError(
            "The workflow version is already active", code="workflow_already_published"
        )
    _validate(
        session,
        {
            "stages": [
                {
                    "key": item.key,
                    "ordinal": item.ordinal,
                    "is_initial": item.is_initial,
                    "entry_prerequisites": item.entry_prerequisites,
                }
                for item in session.scalars(
                    select(WorkflowStage).where(WorkflowStage.template_version_id == version.id)
                )
            ],
            "transitions": [
                {
                    "key": item.key,
                    "from_stage_key": item.from_stage_key,
                    "to_stage_key": item.to_stage_key,
                    "required_permission": item.required_permission,
                    "authorized_role_keys": item.authorized_role_keys,
                }
                for item in session.scalars(
                    select(WorkflowTransition).where(
                        WorkflowTransition.template_version_id == version.id
                    )
                )
            ],
        },
    )
    version.is_published = True
    record_audit_event(
        session,
        actor=principal,
        action="WORKFLOW_VERSION_PUBLISHED",
        entity_type="WORKFLOW_TEMPLATE_VERSION",
        entity_id=str(version.id),
        correlation_id=correlation_id,
        after_summary={"existing_applications_remain_pinned": True},
    )
    return version
