"""Idempotent synthetic development data. Never invoke this against production."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import (
    Application,
    ApplicationStageHistory,
    ApplicationVersion,
    AuditEvent,
    CatalogueRequirement,
    Document,
    DocumentVersion,
    GuidanceSource,
    GuidanceSourceVersion,
    Institution,
    Notification,
    OutboxEvent,
    Permission,
    Region,
    Role,
    RoleAssignment,
    RolePermission,
    User,
    WorkflowStage,
    WorkflowTemplate,
    WorkflowTemplateVersion,
    WorkflowTransition,
)
from app.permissions.access import build_principal
from app.services.audit import record_audit_event
from app.storage import LocalPrivateStorage

DEMO_PASSWORD = os.environ.get("DEVELOPMENT_SEED_PASSWORD", "")


def _development_seed_password() -> str:
    password = DEMO_PASSWORD.strip()
    if len(password) < 12 or password.lower().startswith("replace-"):
        raise RuntimeError(
            "Set DEVELOPMENT_SEED_PASSWORD to a unique local synthetic password before seeding"
        )
    return password

PERMISSIONS = {
    "application.read": "Read applications within an authorized scope",
    "application.write": "Create and update draft applications",
    "application.submit": "Submit an authorized draft application",
    "workflow.transition": "Execute an authorized configured workflow transition",
    "scrutiny.review": "Create synthetic scrutiny reviews and findings",
    "deficiency.manage": "Return an application with documented deficiencies",
    "scrutiny.assign": "Assign or revoke synthetic application reviewers",
    "evc.schedule": "Coordinate synthetic EVC visits",
    "compliance.manage": "Create and submit synthetic compliance obligations",
    "compliance.verify": "Review synthetic compliance evidence and validity",
    "document.read": "Read document metadata",
    "document.write": "Upload document versions",
    "document.download": "Download authorized private documents",
    "audit.read": "Read authorized audit history",
    "workflow-template.manage": "Manage workflow configurations",
    "user.manage": "Manage users and scoped role grants",
    "diagnostics.read": "Read operational diagnostics",
    "guidance.read": "Read guidance sources and catalogue requirements",
    "guidance.manage": "Draft guidance sources and catalogue requirements",
    "guidance.review": "Approve, supersede, or archive guidance and requirements",
    "mapping.propose": "Propose a requirement-to-evidence mapping",
    "mapping.review": "Confirm, reject, or supersede a requirement-to-evidence mapping",
    "guidance.ingest": "Attach and process authorized private guidance documents",
    "guidance.extract.review": "Review, correct, and approve guidance extraction runs",
    "committee.manage": "Create committee reviews and assign members",
    "committee.review": "Submit an assigned committee review",
    "committee.finalize": "Consolidate committee recommendations",
    "decision.record": "Record an authorized advisory-independent decision",
    "communication.manage": "Create and edit communication drafts",
    "communication.approve": "Approve and queue communication drafts",
}

ROLE_PERMISSIONS = {
    "INSTITUTION_APPLICANT": {
        "application.read",
        "application.write",
        "application.submit",
        "document.read",
        "document.write",
        "document.download",
        "compliance.manage",
        "guidance.read",
        "mapping.propose",
    },
    "INSTITUTION_ADMINISTRATOR": {
        "application.read",
        "application.write",
        "application.submit",
        "document.read",
        "document.write",
        "document.download",
        "compliance.manage",
        "guidance.read",
        "mapping.propose",
    },
    "SCRUTINY_OFFICER": {
        "application.read",
        "document.read",
        "document.download",
        "workflow.transition",
        "scrutiny.review",
        "deficiency.manage",
        "guidance.read",
        "mapping.propose",
        "mapping.review",
        "committee.review",
    },
    "REGIONAL_OFFICER": {
        "application.read",
        "document.read",
        "document.download",
        "workflow.transition",
        "scrutiny.review",
        "deficiency.manage",
        "scrutiny.assign",
        "guidance.read",
        "mapping.propose",
        "mapping.review",
        "guidance.ingest",
        "guidance.extract.review",
        "committee.manage",
        "committee.finalize",
        "decision.record",
        "communication.manage",
        "communication.approve",
    },
    "REGIONAL_ADMINISTRATOR": {
        "application.read",
        "document.read",
        "document.download",
        "workflow.transition",
        "guidance.read",
    },
    "EVC_MEMBER": {
        "application.read",
        "document.read",
        "document.download",
        "guidance.read",
        "mapping.propose",
    },
    "EVC_COORDINATOR": {
        "application.read",
        "document.read",
        "document.download",
        "evc.schedule",
        "guidance.read",
        "mapping.propose",
        "mapping.review",
    },
    "AUTHORIZED_REVIEWER": {
        "application.read",
        "document.read",
        "document.download",
        "guidance.read",
        "mapping.propose",
        "mapping.review",
    },
    "COMPLIANCE_OFFICER": {
        "application.read",
        "document.read",
        "document.download",
        "compliance.manage",
        "compliance.verify",
        "guidance.read",
        "mapping.propose",
        "mapping.review",
    },
    "SYSTEM_ADMINISTRATOR": {
        "audit.read",
        "workflow-template.manage",
        "user.manage",
        "diagnostics.read",
        "guidance.read",
        "guidance.manage",
        "guidance.review",
        "mapping.propose",
        "mapping.review",
        "guidance.ingest",
        "guidance.extract.review",
        "document.read",
        "document.download",
    },
    "READ_ONLY_AUDITOR": {"application.read", "audit.read", "guidance.read"},
}

ROLE_NAMES = {
    "INSTITUTION_APPLICANT": "Institution Applicant",
    "INSTITUTION_ADMINISTRATOR": "Institution Administrator",
    "SCRUTINY_OFFICER": "Scrutiny Officer",
    "REGIONAL_OFFICER": "Regional Officer",
    "REGIONAL_ADMINISTRATOR": "Regional Administrator",
    "EVC_MEMBER": "EVC Member",
    "EVC_COORDINATOR": "EVC Coordinator",
    "AUTHORIZED_REVIEWER": "Authorized SAC/SHC Reviewer",
    "COMPLIANCE_OFFICER": "Compliance Officer",
    "SYSTEM_ADMINISTRATOR": "System Administrator",
    "READ_ONLY_AUDITOR": "Read-only Auditor",
}

ROUTES = {
    "SCRUTINY_ONLY": ["draft", "submitted", "scrutiny", "returned", "completed"],
    "SCRUTINY_THEN_EVC": ["draft", "submitted", "scrutiny", "returned", "evc", "completed"],
    "EVC_THEN_SAC_SHC": ["draft", "submitted", "evc", "sac_shc", "completed"],
    "SCRUTINY_EVC_SAC_SHC": [
        "draft",
        "submitted",
        "scrutiny",
        "returned",
        "evc",
        "sac_shc",
        "completed",
    ],
}


def _checksum(data: dict[str, object]) -> str:
    return sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _get_or_create(session: object, model: object, **values: object) -> tuple[object, bool]:
    # Kept deliberately small so seeding is idempotent without destructive resets.
    key = "key" if "key" in values else "code" if "code" in values else "email"
    existing = session.scalar(select(model).where(getattr(model, key) == values[key]))  # type: ignore[arg-type, union-attr]
    if existing is not None:
        return existing, False
    instance = model(**values)  # type: ignore[operator]
    session.add(instance)  # type: ignore[union-attr]
    session.flush()  # type: ignore[union-attr]
    return instance, True


def _seed_workflow(session: object, route_key: str) -> WorkflowTemplateVersion:
    template, _ = _get_or_create(
        session,
        WorkflowTemplate,
        key=route_key,
        name=route_key.replace("_", " ").title(),
        description="Synthetic demonstration configuration; not an official AICTE route.",
        is_active=True,
    )
    version = session.scalar(
        select(WorkflowTemplateVersion).where(
            WorkflowTemplateVersion.template_id == template.id,
            WorkflowTemplateVersion.version_number == 1,
        )
    )
    if version is None:
        version = WorkflowTemplateVersion(
            template_id=template.id,
            version_number=1,
            route_type=route_key,
            verification_status="SYNTHETIC_CONFIGURATION",
            source_reference="Phase 2 synthetic demonstration configuration",
            is_published=True,
            configuration={"synthetic": True, "route_key": route_key},
        )
        session.add(version)
        session.flush()
    stages = ROUTES[route_key]
    for index, stage_key in enumerate(stages, start=1):
        existing = session.scalar(
            select(WorkflowStage).where(
                WorkflowStage.template_version_id == version.id,
                WorkflowStage.key == stage_key,
            )
        )
        if existing is None:
            session.add(
                WorkflowStage(
                    template_version_id=version.id,
                    key=stage_key,
                    display_name=stage_key.replace("_", " ").title(),
                    ordinal=index * 10,
                    is_initial=stage_key == "draft",
                    entry_prerequisites=[],
                )
            )
    session.flush()
    progression_stages = [stage for stage in stages if stage != "returned"]
    for from_key, to_key in zip(progression_stages, progression_stages[1:], strict=False):
        transition_key = "submit" if from_key == "draft" else f"advance_to_{to_key}"
        existing = session.scalar(
            select(WorkflowTransition).where(
                WorkflowTransition.template_version_id == version.id,
                WorkflowTransition.key == transition_key,
            )
        )
        if existing is None:
            is_submit = transition_key == "submit"
            session.add(
                WorkflowTransition(
                    template_version_id=version.id,
                    key=transition_key,
                    from_stage_key=from_key,
                    to_stage_key=to_key,
                    required_permission="application.submit"
                    if is_submit
                    else "workflow.transition",
                    authorized_role_keys=(
                        ["INSTITUTION_APPLICANT", "INSTITUTION_ADMINISTRATOR"]
                        if is_submit
                        else ["REGIONAL_OFFICER", "REGIONAL_ADMINISTRATOR"]
                    ),
                    prerequisites=(
                        {
                            "all": [
                                {"fact": "application.required_fields"},
                                {"fact": "documents.minimum_count", "minimum": 1},
                            ]
                        }
                        if is_submit
                        else {}
                    ),
                    blocking_conditions={},
                    explanation=(
                        "The synthetic application has required fields and at least one document."
                        if is_submit
                        else (
                            "A human officer may move this synthetic route to its next "
                            "configured stage."
                        )
                    ),
                )
            )
    if "scrutiny" in stages and "returned" in stages:
        configured_returns = (
            (
                "return_for_correction",
                "scrutiny",
                "returned",
                "deficiency.manage",
                ["SCRUTINY_OFFICER", "REGIONAL_OFFICER"],
                {},
                (
                    "An authorized human reviewer may return this synthetic case with "
                    "documented deficiencies."
                ),
            ),
            (
                "resubmit_after_correction",
                "returned",
                "scrutiny",
                "application.submit",
                ["INSTITUTION_APPLICANT", "INSTITUTION_ADMINISTRATOR"],
                {"fact": "deficiencies.all_responded"},
                "The institution has responded to every recorded synthetic deficiency.",
            ),
        )
        for (
            transition_key,
            from_key,
            to_key,
            permission,
            roles,
            prerequisites,
            explanation,
        ) in configured_returns:
            existing = session.scalar(
                select(WorkflowTransition).where(
                    WorkflowTransition.template_version_id == version.id,
                    WorkflowTransition.key == transition_key,
                )
            )
            if existing is None:
                session.add(
                    WorkflowTransition(
                        template_version_id=version.id,
                        key=transition_key,
                        from_stage_key=from_key,
                        to_stage_key=to_key,
                        required_permission=permission,
                        authorized_role_keys=roles,
                        prerequisites=prerequisites,
                        blocking_conditions={},
                        explanation=explanation,
                    )
                )
    session.flush()
    return version


def _ensure_role_assignment(
    session: object,
    *,
    user: User,
    role: Role,
    scope_type: str,
    institution_id: object | None = None,
    region_id: object | None = None,
) -> None:
    existing = session.scalar(
        select(RoleAssignment).where(
            RoleAssignment.user_id == user.id,
            RoleAssignment.role_id == role.id,
            RoleAssignment.scope_type == scope_type,
            RoleAssignment.institution_id == institution_id,
            RoleAssignment.region_id == region_id,
            RoleAssignment.is_active.is_(True),
        )
    )
    if existing is None:
        session.add(
            RoleAssignment(
                user_id=user.id,
                role_id=role.id,
                scope_type=scope_type,
                institution_id=institution_id,
                region_id=region_id,
                is_active=True,
            )
        )


def _seed_document(
    session: object, application: Application, user: User, storage: LocalPrivateStorage
) -> None:
    existing = session.scalar(select(Document).where(Document.application_id == application.id))
    if existing is not None:
        return
    document = Document(
        institution_id=application.institution_id,
        application_id=application.id,
        classification="SYNTHETIC_DEMO",
        current_version_number=1,
        status="AVAILABLE",
    )
    session.add(document)
    session.flush()
    content = b"%PDF-1.4\n% Synthetic FlowTrack demonstration document\n%%EOF\n"
    checksum = sha256(content).hexdigest()
    storage_key = f"documents/{application.institution_id}/{document.id}/1-seed"
    if not storage.exists(storage_key):
        storage.store(storage_key, content)
    session.add(
        DocumentVersion(
            document_id=document.id,
            version_number=1,
            original_filename="synthetic-evidence.pdf",
            storage_key=storage_key,
            mime_type="application/pdf",
            size_bytes=len(content),
            checksum_sha256=checksum,
            uploaded_by_user_id=user.id,
            processing_status="NOT_REQUESTED",
        )
    )


def seed() -> dict[str, int]:
    settings = get_settings()
    if settings.environment == "production" or not settings.development_seed_enabled:
        raise RuntimeError(
            "Synthetic seeding is disabled. Set ENVIRONMENT=development and "
            "ENABLE_DEVELOPMENT_SEED=true."
        )
    development_password = _development_seed_password()
    storage = LocalPrivateStorage(settings.private_storage_root)
    with SessionLocal() as session:
        north, _ = _get_or_create(
            session, Region, code="DEMO-NORTH", name="Demo North Region", is_active=True
        )
        south, _ = _get_or_create(
            session, Region, code="DEMO-SOUTH", name="Demo South Region", is_active=True
        )
        alpha, _ = _get_or_create(
            session,
            Institution,
            code="DEMO-ALPHA",
            name="Demo Alpha Institute",
            region_id=north.id,
            is_active=True,
        )
        beta, _ = _get_or_create(
            session,
            Institution,
            code="DEMO-BETA",
            name="Demo Beta Institute",
            region_id=south.id,
            is_active=True,
        )
        permissions: dict[str, Permission] = {}
        for code, description in PERMISSIONS.items():
            permission, _ = _get_or_create(session, Permission, code=code, description=description)
            permissions[code] = permission
        roles: dict[str, Role] = {}
        for key, name in ROLE_NAMES.items():
            role, _ = _get_or_create(
                session,
                Role,
                key=key,
                name=name,
                description=f"Synthetic {name} role",
                is_active=True,
            )
            roles[key] = role
            for permission_code in ROLE_PERMISSIONS[key]:
                link = session.get(RolePermission, (role.id, permissions[permission_code].id))
                if link is None:
                    session.add(
                        RolePermission(
                            role_id=role.id, permission_id=permissions[permission_code].id
                        )
                    )
        session.flush()

        account_specs = [
            (
                "applicant.alpha@example.org",
                "Alpha Applicant",
                "INSTITUTION_APPLICANT",
                "INSTITUTION",
                alpha.id,
                None,
            ),
            (
                "applicant.beta@example.org",
                "Beta Applicant",
                "INSTITUTION_ADMINISTRATOR",
                "INSTITUTION",
                beta.id,
                None,
            ),
            (
                "regional.north@example.org",
                "North Regional Officer",
                "REGIONAL_OFFICER",
                "REGION",
                None,
                north.id,
            ),
            (
                "regional.south@example.org",
                "South Regional Officer",
                "REGIONAL_OFFICER",
                "REGION",
                None,
                south.id,
            ),
            (
                "scrutiny.north@example.org",
                "North Scrutiny Officer",
                "SCRUTINY_OFFICER",
                "REGION",
                None,
                north.id,
            ),
            (
                "scrutiny.north.alt@example.org",
                "North Alternate Scrutiny Officer",
                "SCRUTINY_OFFICER",
                "REGION",
                None,
                north.id,
            ),
            (
                "evc.south@example.org",
                "South EVC Coordinator",
                "EVC_COORDINATOR",
                "REGION",
                None,
                south.id,
            ),
            (
                "compliance.south@example.org",
                "South Compliance Officer",
                "COMPLIANCE_OFFICER",
                "REGION",
                None,
                south.id,
            ),
            ("auditor@example.org", "Demo Auditor", "READ_ONLY_AUDITOR", "GLOBAL", None, None),
            (
                "admin@example.org",
                "Demo System Administrator",
                "SYSTEM_ADMINISTRATOR",
                "GLOBAL",
                None,
                None,
            ),
        ]
        users: dict[str, User] = {}
        for email, display_name, role_key, scope_type, institution_id, region_id in account_specs:
            user = session.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(
                    email=email,
                    display_name=display_name,
                    password_hash=hash_password(development_password),
                    is_active=True,
                )
                session.add(user)
                session.flush()
            users[email] = user
            _ensure_role_assignment(
                session,
                user=user,
                role=roles[role_key],
                scope_type=scope_type,
                institution_id=institution_id,
                region_id=region_id,
            )
        session.flush()
        workflows = {key: _seed_workflow(session, key) for key in ROUTES}
        guidance = session.scalar(
            select(GuidanceSource).where(GuidanceSource.key == "DEMO-GUIDANCE")
        )
        if guidance is None:
            guidance = GuidanceSource(
                key="DEMO-GUIDANCE",
                title="Synthetic CaseConnect demonstration guidance",
                source_type="DEMONSTRATION_GUIDANCE",
                issuing_organization="CaseConnect development seed",
                source_reference=None,
                provenance={"synthetic": True, "notice": "Not an AICTE or statutory source."},
                created_by_user_id=users["admin@example.org"].id,
            )
            session.add(guidance)
            session.flush()
            guidance_version = GuidanceSourceVersion(
                source_id=guidance.id,
                version_number=1,
                version_label="demo-1.0",
                status="APPROVED",
                verification_status="SYNTHETIC_DEMONSTRATION",
                upload_metadata={"synthetic": True, "text_ingested": False},
                created_by_user_id=users["admin@example.org"].id,
                reviewed_by_user_id=users["admin@example.org"].id,
                reviewed_at=datetime.now(UTC),
            )
            session.add(guidance_version)
            session.flush()
            session.add(
                CatalogueRequirement(
                    stable_identifier="DEMO.APPLICATION.DOCUMENT",
                    version_number=1,
                    source_version_id=guidance_version.id,
                    title="Demonstration application document",
                    description=(
                        "Synthetic demonstration requirement used only to show "
                        "human-reviewed mapping."
                    ),
                    category="APPLICATION_DOCUMENTATION",
                    module_key="APPLICATION",
                    section_reference="Demo section 1",
                    applicability_conditions={"synthetic": True},
                    evidence_metadata={"expected": "private document version"},
                    status="APPROVED",
                    created_by_user_id=users["admin@example.org"].id,
                    reviewed_by_user_id=users["admin@example.org"].id,
                    reviewed_at=datetime.now(UTC),
                )
            )

        def draft_application(
            reference: str, institution: Institution, workflow: WorkflowTemplateVersion, title: str
        ) -> Application:
            application = session.scalar(
                select(Application).where(Application.reference_number == reference)
            )
            if application is not None:
                return application
            data = {
                "title": title,
                "application_type": "SYNTHETIC_NEW_PROGRAMME",
                "synthetic": True,
            }
            application = Application(
                institution_id=institution.id,
                assigned_region_id=institution.region_id,
                workflow_template_version_id=workflow.id,
                reference_number=reference,
                application_type="SYNTHETIC_NEW_PROGRAMME",
                title=title,
                status="DRAFT",
                current_stage_key="draft",
                current_version_number=1,
                row_version=1,
            )
            session.add(application)
            session.flush()
            session.add(
                ApplicationVersion(
                    application_id=application.id,
                    version_number=1,
                    data=data,
                    checksum=_checksum(data),
                )
            )
            session.add(
                ApplicationStageHistory(
                    application_id=application.id,
                    sequence=1,
                    transition_key="CREATE_DRAFT",
                    from_stage_key=None,
                    to_stage_key="draft",
                    actor_id=users["applicant.alpha@example.org"].id,
                    facts={"synthetic": True},
                )
            )
            return application

        draft_application(
            "DEMO-APP-ALPHA-DRAFT", alpha, workflows["SCRUTINY_ONLY"], "Synthetic Alpha Draft"
        )
        alpha_submitted = draft_application(
            "DEMO-APP-ALPHA-SUBMITTED",
            alpha,
            workflows["SCRUTINY_THEN_EVC"],
            "Synthetic Alpha Submitted",
        )
        _seed_document(session, alpha_submitted, users["applicant.alpha@example.org"], storage)
        if alpha_submitted.status == "DRAFT":
            alpha_submitted.status = "SUBMITTED"
            alpha_submitted.current_stage_key = "submitted"
            alpha_submitted.submitted_at = datetime.now(UTC)
            alpha_submitted.submitted_by_user_id = users["applicant.alpha@example.org"].id
            alpha_submitted.current_version_number = 2
            alpha_submitted.row_version = 2
            submission_data = {
                "title": alpha_submitted.title,
                "application_type": alpha_submitted.application_type,
                "synthetic": True,
            }
            session.add(
                ApplicationVersion(
                    application_id=alpha_submitted.id,
                    version_number=2,
                    data=submission_data,
                    checksum=_checksum(submission_data),
                    is_submission_snapshot=True,
                    submitted_at=alpha_submitted.submitted_at,
                    submitted_by_user_id=alpha_submitted.submitted_by_user_id,
                )
            )
            session.add(
                ApplicationStageHistory(
                    application_id=alpha_submitted.id,
                    sequence=2,
                    transition_key="submit",
                    from_stage_key="draft",
                    to_stage_key="submitted",
                    actor_id=users["applicant.alpha@example.org"].id,
                    facts={"synthetic": True, "seeded": True},
                )
            )
        beta_progress = draft_application(
            "DEMO-APP-BETA-EVC", beta, workflows["EVC_THEN_SAC_SHC"], "Synthetic Beta EVC Route"
        )
        _seed_document(session, beta_progress, users["applicant.beta@example.org"], storage)
        if beta_progress.status == "DRAFT":
            beta_progress.status = "IN_REVIEW"
            beta_progress.current_stage_key = "evc"
            beta_progress.submitted_at = datetime.now(UTC)
            beta_progress.submitted_by_user_id = users["applicant.beta@example.org"].id
            beta_progress.current_version_number = 2
            beta_progress.row_version = 3
            data = {
                "title": beta_progress.title,
                "application_type": beta_progress.application_type,
                "synthetic": True,
            }
            session.add(
                ApplicationVersion(
                    application_id=beta_progress.id,
                    version_number=2,
                    data=data,
                    checksum=_checksum(data),
                    is_submission_snapshot=True,
                    submitted_at=beta_progress.submitted_at,
                    submitted_by_user_id=beta_progress.submitted_by_user_id,
                )
            )
            session.add_all(
                [
                    ApplicationStageHistory(
                        application_id=beta_progress.id,
                        sequence=2,
                        transition_key="submit",
                        from_stage_key="draft",
                        to_stage_key="submitted",
                        actor_id=users["applicant.beta@example.org"].id,
                        facts={"synthetic": True, "seeded": True},
                    ),
                    ApplicationStageHistory(
                        application_id=beta_progress.id,
                        sequence=3,
                        transition_key="advance_to_evc",
                        from_stage_key="submitted",
                        to_stage_key="evc",
                        actor_id=users["regional.south@example.org"].id,
                        facts={"synthetic": True, "seeded": True},
                    ),
                ]
            )
        session.flush()
        submitter = build_principal(session, users["applicant.alpha@example.org"])
        existing_event = session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.idempotency_key == "seed:alpha-submitted:notification"
            )
        )
        if existing_event is None:
            existing_event = OutboxEvent(
                event_type="APPLICATION_SUBMITTED",
                aggregate_type="APPLICATION",
                aggregate_id=str(alpha_submitted.id),
                aggregate_version=alpha_submitted.row_version,
                payload={"synthetic": True},
                status="PROCESSED",
                processed_at=datetime.now(UTC),
                idempotency_key="seed:alpha-submitted:notification",
            )
            session.add(existing_event)
            session.flush()
            session.add(
                Notification(
                    user_id=users["applicant.alpha@example.org"].id,
                    outbox_event_id=existing_event.id,
                    title="Synthetic application submitted",
                    body="This is seeded demonstration data, not an official notification.",
                    status="UNREAD",
                )
            )
        if not session.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "SYNTHETIC_SEED_COMPLETED",
                AuditEvent.entity_id == "phase-2-seed",
            )
        ):
            record_audit_event(
                session,
                actor=submitter,
                action="SYNTHETIC_SEED_COMPLETED",
                entity_type="VALIDATION_CENTER",
                entity_id="phase-2-seed",
                after_summary={"synthetic": True},
            )
        session.commit()
        return {
            "regions": int(session.scalar(select(func.count(Region.id))) or 0),
            "institutions": int(session.scalar(select(func.count(Institution.id))) or 0),
            "users": int(session.scalar(select(func.count(User.id))) or 0),
            "applications": int(session.scalar(select(func.count(Application.id))) or 0),
        }


if __name__ == "__main__":
    print(json.dumps(seed(), sort_keys=True))
