from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, DomainError, NotFoundError
from app.models import (
    Application,
    CatalogueRequirement,
    ComplianceEvidence,
    ComplianceObligation,
    DocumentVersion,
    EvcEvidenceLink,
    EvcVisit,
    GuidanceSource,
    GuidanceSourceVersion,
    RequirementEvidenceMapping,
)
from app.permissions.access import Principal, require_application_access, require_permission
from app.services.audit import record_audit_event
from app.services.documents import get_document


def _source(session: Session, source_id: UUID) -> GuidanceSource:
    item = session.get(GuidanceSource, source_id)
    if item is None:
        raise NotFoundError("The requested guidance source was not found")
    return item


def _version(session: Session, version_id: UUID) -> GuidanceSourceVersion:
    item = session.get(GuidanceSourceVersion, version_id)
    if item is None:
        raise NotFoundError("The requested guidance version was not found")
    return item


def _requirement(session: Session, requirement_id: UUID) -> CatalogueRequirement:
    item = session.get(CatalogueRequirement, requirement_id)
    if item is None:
        raise NotFoundError("The requested catalogue requirement was not found")
    return item


def _mapping(session: Session, mapping_id: UUID) -> RequirementEvidenceMapping:
    item = session.get(RequirementEvidenceMapping, mapping_id)
    if item is None:
        raise NotFoundError("The requested evidence mapping was not found")
    return item


def _source_version_summary(item: GuidanceSourceVersion) -> dict[str, object]:
    return {
        "id": str(item.id),
        "version_number": item.version_number,
        "version_label": item.version_label,
        "effective_date": item.effective_date.isoformat() if item.effective_date else None,
        "content_hash": item.content_hash,
        "status": item.status,
        "verification_status": item.verification_status,
        "reviewed_by_user_id": str(item.reviewed_by_user_id) if item.reviewed_by_user_id else None,
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
        "created_at": item.created_at.isoformat(),
    }


def list_sources(session: Session, *, principal: Principal) -> list[dict[str, object]]:
    require_permission(principal, "guidance.read")
    sources = list(session.scalars(select(GuidanceSource).order_by(GuidanceSource.title)))
    return [
        {
            "id": str(source.id),
            "key": source.key,
            "title": source.title,
            "source_type": source.source_type,
            "issuing_organization": source.issuing_organization,
            "source_reference": source.source_reference,
            "versions": [
                _source_version_summary(version)
                for version in session.scalars(
                    select(GuidanceSourceVersion)
                    .where(GuidanceSourceVersion.source_id == source.id)
                    .order_by(GuidanceSourceVersion.version_number.desc())
                )
            ],
        }
        for source in sources
    ]


def source_detail(session: Session, *, source_id: UUID, principal: Principal) -> dict[str, object]:
    require_permission(principal, "guidance.read")
    source = _source(session, source_id)
    return {
        "id": str(source.id),
        "key": source.key,
        "title": source.title,
        "source_type": source.source_type,
        "issuing_organization": source.issuing_organization,
        "source_reference": source.source_reference,
        "provenance": source.provenance,
        "created_by_user_id": str(source.created_by_user_id),
        "versions": [
            _source_version_summary(item)
            for item in session.scalars(
                select(GuidanceSourceVersion)
                .where(GuidanceSourceVersion.source_id == source.id)
                .order_by(GuidanceSourceVersion.version_number.desc())
            )
        ],
    }


def create_source(
    session: Session, *, data: dict[str, object], principal: Principal, correlation_id: str | None
) -> GuidanceSource:
    require_permission(principal, "guidance.manage")
    if (
        session.scalar(select(GuidanceSource.id).where(GuidanceSource.key == data["key"]))
        is not None
    ):
        raise ConflictError(
            "A guidance source already uses this key", code="duplicate_guidance_key"
        )
    source = GuidanceSource(
        id=uuid4(),
        key=str(data["key"]),
        title=str(data["title"]),
        source_type=str(data["source_type"]),
        issuing_organization=data.get("issuing_organization"),
        source_reference=data.get("source_reference"),
        provenance=dict(data.get("provenance") or {}),
        created_by_user_id=principal.user.id,
    )
    session.add(source)
    session.flush()
    version = GuidanceSourceVersion(
        id=uuid4(),
        source_id=source.id,
        version_number=1,
        version_label=str(data["version_label"]),
        effective_date=data.get("effective_date"),
        content_hash=data.get("content_hash"),
        upload_metadata=dict(data.get("upload_metadata") or {}),
        verification_status=str(data["verification_status"]),
        status="DRAFT",
        created_by_user_id=principal.user.id,
    )
    session.add(version)
    record_audit_event(
        session,
        actor=principal,
        action="GUIDANCE_SOURCE_CREATED",
        entity_type="GUIDANCE_SOURCE",
        entity_id=str(source.id),
        correlation_id=correlation_id,
        after_summary={
            "key": source.key,
            "verification_status": version.verification_status,
            "version": 1,
        },
    )
    return source


def create_source_version(
    session: Session,
    *,
    source_id: UUID,
    data: dict[str, object],
    principal: Principal,
    correlation_id: str | None,
) -> GuidanceSourceVersion:
    require_permission(principal, "guidance.manage")
    _source(session, source_id)
    latest = (
        session.scalar(
            select(func.max(GuidanceSourceVersion.version_number)).where(
                GuidanceSourceVersion.source_id == source_id
            )
        )
        or 0
    )
    item = GuidanceSourceVersion(
        id=uuid4(),
        source_id=source_id,
        version_number=int(latest) + 1,
        version_label=str(data["version_label"]),
        effective_date=data.get("effective_date"),
        content_hash=data.get("content_hash"),
        upload_metadata=dict(data.get("upload_metadata") or {}),
        verification_status=str(data["verification_status"]),
        status="DRAFT",
        created_by_user_id=principal.user.id,
    )
    session.add(item)
    record_audit_event(
        session,
        actor=principal,
        action="GUIDANCE_VERSION_CREATED",
        entity_type="GUIDANCE_SOURCE_VERSION",
        entity_id=str(item.id),
        correlation_id=correlation_id,
        after_summary={"source_id": str(source_id), "version": item.version_number},
    )
    return item


def action_source_version(
    session: Session,
    *,
    version_id: UUID,
    action: str,
    reason: str | None,
    principal: Principal,
    correlation_id: str | None,
) -> GuidanceSourceVersion:
    item = _version(session, version_id)
    action = action.upper()
    before = item.status
    if action == "SUBMIT":
        require_permission(principal, "guidance.manage")
        if item.status != "DRAFT":
            raise ConflictError(
                "Only a draft guidance version can be submitted", code="invalid_guidance_transition"
            )
        item.status = "SUBMITTED"
    elif action == "APPROVE":
        require_permission(principal, "guidance.review")
        if item.status != "SUBMITTED":
            raise ConflictError(
                "Only a submitted guidance version can be approved",
                code="invalid_guidance_transition",
            )
        if item.verification_status not in {"SYNTHETIC_DEMONSTRATION", "VERIFIED_OFFICIAL"}:
            raise DomainError(
                422, "invalid_verification_status", "Guidance verification status is invalid"
            )
        if item.verification_status == "VERIFIED_OFFICIAL" and not (reason or "").strip():
            raise DomainError(
                422,
                "verification_reason_required",
                "A verified official source requires a review reason or reference.",
            )
        item.status = "APPROVED"
        item.reviewed_by_user_id = principal.user.id
        item.reviewed_at = datetime.now(UTC)
    elif action == "SUPERSEDE":
        require_permission(principal, "guidance.review")
        if item.status != "APPROVED":
            raise ConflictError(
                "Only approved guidance can be superseded", code="invalid_guidance_transition"
            )
        item.status = "SUPERSEDED"
        item.reviewed_by_user_id = principal.user.id
        item.reviewed_at = datetime.now(UTC)
    elif action == "ARCHIVE":
        require_permission(principal, "guidance.review")
        if item.status not in {"DRAFT", "SUBMITTED", "APPROVED", "SUPERSEDED"}:
            raise ConflictError(
                "This guidance version cannot be archived", code="invalid_guidance_transition"
            )
        item.status = "ARCHIVED"
        item.reviewed_by_user_id = principal.user.id
        item.reviewed_at = datetime.now(UTC)
    else:
        raise DomainError(422, "invalid_guidance_action", "Unsupported guidance lifecycle action")
    record_audit_event(
        session,
        actor=principal,
        action=f"GUIDANCE_VERSION_{action}",
        entity_type="GUIDANCE_SOURCE_VERSION",
        entity_id=str(item.id),
        correlation_id=correlation_id,
        reason=reason,
        before_summary={"status": before},
        after_summary={"status": item.status, "verification_status": item.verification_status},
    )
    return item


def list_requirements(
    session: Session,
    *,
    principal: Principal,
    source_version_id: UUID | None = None,
    category: str | None = None,
    module_key: str | None = None,
    status: str | None = None,
) -> list[CatalogueRequirement]:
    require_permission(principal, "guidance.read")
    query = select(CatalogueRequirement).order_by(
        CatalogueRequirement.stable_identifier, CatalogueRequirement.version_number.desc()
    )
    if source_version_id:
        query = query.where(CatalogueRequirement.source_version_id == source_version_id)
    if category:
        query = query.where(CatalogueRequirement.category == category)
    if module_key:
        query = query.where(CatalogueRequirement.module_key == module_key)
    if status:
        query = query.where(CatalogueRequirement.status == status.upper())
    return list(session.scalars(query))


def get_requirement(
    session: Session, *, requirement_id: UUID, principal: Principal
) -> CatalogueRequirement:
    require_permission(principal, "guidance.read")
    return _requirement(session, requirement_id)


def create_requirement(
    session: Session, *, data: dict[str, object], principal: Principal, correlation_id: str | None
) -> CatalogueRequirement:
    require_permission(principal, "guidance.manage")
    _version(session, UUID(str(data["source_version_id"])))
    stable = str(data["stable_identifier"])
    next_version = (
        int(
            session.scalar(
                select(func.max(CatalogueRequirement.version_number)).where(
                    CatalogueRequirement.stable_identifier == stable
                )
            )
            or 0
        )
        + 1
    )
    supersedes = data.get("supersedes_requirement_id")
    if supersedes:
        prior = _requirement(session, UUID(str(supersedes)))
        if prior.stable_identifier != stable:
            raise DomainError(
                422,
                "requirement_lineage_mismatch",
                "A replacement must retain the stable requirement identifier",
            )
    item = CatalogueRequirement(
        id=uuid4(),
        stable_identifier=stable,
        version_number=next_version,
        source_version_id=UUID(str(data["source_version_id"])),
        title=str(data["title"]),
        description=str(data["description"]),
        category=str(data["category"]),
        module_key=str(data["module_key"]),
        section_reference=data.get("section_reference"),
        applicability_conditions=dict(data.get("applicability_conditions") or {}),
        evidence_metadata=dict(data.get("evidence_metadata") or {}),
        severity=data.get("severity"),
        status="DRAFT",
        created_by_user_id=principal.user.id,
        supersedes_requirement_id=UUID(str(supersedes)) if supersedes else None,
    )
    session.add(item)
    record_audit_event(
        session,
        actor=principal,
        action="CATALOGUE_REQUIREMENT_CREATED",
        entity_type="CATALOGUE_REQUIREMENT",
        entity_id=str(item.id),
        correlation_id=correlation_id,
        after_summary={
            "identifier": stable,
            "version": next_version,
            "source_version_id": str(item.source_version_id),
        },
    )
    return item


def action_requirement(
    session: Session,
    *,
    requirement_id: UUID,
    action: str,
    reason: str | None,
    principal: Principal,
    correlation_id: str | None,
) -> CatalogueRequirement:
    item = _requirement(session, requirement_id)
    action = action.upper()
    before = item.status
    if action == "SUBMIT":
        require_permission(principal, "guidance.manage")
        if item.status != "DRAFT":
            raise ConflictError(
                "Only a draft requirement can be submitted", code="invalid_requirement_transition"
            )
        item.status = "SUBMITTED"
    elif action == "APPROVE":
        require_permission(principal, "guidance.review")
        source_version = _version(session, item.source_version_id)
        if item.status != "SUBMITTED" or source_version.status != "APPROVED":
            raise ConflictError(
                "A requirement and its guidance source must both be submitted/approved",
                code="invalid_requirement_transition",
            )
        item.status = "APPROVED"
        item.reviewed_by_user_id = principal.user.id
        item.reviewed_at = datetime.now(UTC)
        if item.supersedes_requirement_id:
            _requirement(session, item.supersedes_requirement_id).status = "SUPERSEDED"
    elif action == "ARCHIVE":
        require_permission(principal, "guidance.review")
        if item.status not in {"DRAFT", "SUBMITTED", "APPROVED", "SUPERSEDED"}:
            raise ConflictError(
                "This requirement cannot be archived", code="invalid_requirement_transition"
            )
        item.status = "ARCHIVED"
        item.reviewed_by_user_id = principal.user.id
        item.reviewed_at = datetime.now(UTC)
    else:
        raise DomainError(
            422, "invalid_requirement_action", "Unsupported requirement lifecycle action"
        )
    record_audit_event(
        session,
        actor=principal,
        action=f"CATALOGUE_REQUIREMENT_{action}",
        entity_type="CATALOGUE_REQUIREMENT",
        entity_id=str(item.id),
        correlation_id=correlation_id,
        reason=reason,
        before_summary={"status": before},
        after_summary={"status": item.status},
    )
    return item


def _mapping_access(
    session: Session, item: RequirementEvidenceMapping, principal: Principal
) -> None:
    app = session.get(Application, item.application_id)
    if app is None:
        raise NotFoundError("The linked application was not found")
    require_application_access(principal, app)
    get_document(session, item.document_id, principal)


def create_mapping(
    session: Session, *, data: dict[str, object], principal: Principal, correlation_id: str | None
) -> RequirementEvidenceMapping:
    require_permission(principal, "mapping.propose")
    requirement = _requirement(session, UUID(str(data["requirement_id"])))
    source_version = _version(session, requirement.source_version_id)
    if requirement.status != "APPROVED" or source_version.status != "APPROVED":
        raise ConflictError(
            "Mappings require an approved requirement and approved guidance",
            code="requirement_not_approved",
        )
    app = session.get(Application, UUID(str(data["application_id"])))
    if app is None:
        raise NotFoundError("The requested application was not found")
    require_application_access(principal, app)
    document = get_document(session, UUID(str(data["document_id"])), principal)
    version = session.get(DocumentVersion, UUID(str(data["document_version_id"])))
    if version is None or version.document_id != document.id:
        raise DomainError(
            422,
            "invalid_document_version",
            "The document version does not belong to the requested document",
        )
    if document.application_id and document.application_id != app.id:
        raise DomainError(
            422,
            "evidence_application_mismatch",
            "The private document is not linked to this application",
        )
    evc_id = data.get("evc_evidence_link_id")
    compliance_id = data.get("compliance_evidence_id")
    if evc_id:
        linked = session.get(EvcEvidenceLink, UUID(str(evc_id)))
        if (
            linked is None
            or linked.document_id != document.id
            or linked.document_version_id != version.id
        ):
            raise DomainError(
                422,
                "invalid_evc_evidence",
                "The EVC evidence does not match the supplied document version",
            )
        visit = session.get(EvcVisit, linked.visit_id)
        if visit is None or visit.application_id != app.id:
            raise DomainError(
                422,
                "evc_evidence_application_mismatch",
                "The EVC evidence is not linked to the requested application",
            )
    if compliance_id:
        linked = session.get(ComplianceEvidence, UUID(str(compliance_id)))
        if (
            linked is None
            or linked.document_id != document.id
            or linked.document_version_id != version.id
        ):
            raise DomainError(
                422,
                "invalid_compliance_evidence",
                "The compliance evidence does not match the supplied document version",
            )
        obligation = session.get(ComplianceObligation, linked.obligation_id)
        if obligation is None or obligation.application_id != app.id:
            raise DomainError(
                422,
                "compliance_evidence_application_mismatch",
                "The compliance evidence is not linked to the requested application",
            )
    supersedes = data.get("supersedes_mapping_id")
    if supersedes:
        previous = _mapping(session, UUID(str(supersedes)))
        _mapping_access(session, previous, principal)
        if previous.requirement_id != requirement.id:
            raise DomainError(
                422,
                "mapping_lineage_mismatch",
                "A replacement mapping must use the same requirement version",
            )
        if previous.status == "PROPOSED":
            raise DomainError(
                422,
                "mapping_supersession_requires_review",
                "Only a reviewed mapping can be superseded by a replacement",
            )
    item = RequirementEvidenceMapping(
        id=uuid4(),
        requirement_id=requirement.id,
        application_id=app.id,
        document_id=document.id,
        document_version_id=version.id,
        evc_evidence_link_id=UUID(str(evc_id)) if evc_id else None,
        compliance_evidence_id=UUID(str(compliance_id)) if compliance_id else None,
        explanation=str(data["explanation"]),
        mapping_method="MANUAL_REVIEW",
        created_by_user_id=principal.user.id,
        supersedes_mapping_id=UUID(str(supersedes)) if supersedes else None,
    )
    session.add(item)
    record_audit_event(
        session,
        actor=principal,
        action="REQUIREMENT_MAPPING_PROPOSED",
        entity_type="REQUIREMENT_EVIDENCE_MAPPING",
        entity_id=str(item.id),
        correlation_id=correlation_id,
        after_summary={
            "requirement_id": str(requirement.id),
            "application_id": str(app.id),
            "document_id": str(document.id),
            "document_version_id": str(version.id),
            "method": item.mapping_method,
        },
    )
    return item


def list_mappings(
    session: Session,
    *,
    principal: Principal,
    application_id: UUID | None = None,
    requirement_id: UUID | None = None,
) -> list[RequirementEvidenceMapping]:
    require_permission(principal, "guidance.read")
    query = select(RequirementEvidenceMapping).order_by(
        RequirementEvidenceMapping.created_at.desc()
    )
    if application_id:
        query = query.where(RequirementEvidenceMapping.application_id == application_id)
    if requirement_id:
        query = query.where(RequirementEvidenceMapping.requirement_id == requirement_id)
    items = list(session.scalars(query))
    visible: list[RequirementEvidenceMapping] = []
    for item in items:
        try:
            _mapping_access(session, item, principal)
        except Exception:
            continue
        visible.append(item)
    return visible


def get_mapping(
    session: Session, *, mapping_id: UUID, principal: Principal
) -> RequirementEvidenceMapping:
    require_permission(principal, "guidance.read")
    item = _mapping(session, mapping_id)
    _mapping_access(session, item, principal)
    return item


def action_mapping(
    session: Session,
    *,
    mapping_id: UUID,
    action: str,
    reason: str | None,
    principal: Principal,
    correlation_id: str | None,
) -> RequirementEvidenceMapping:
    require_permission(principal, "mapping.review")
    item = _mapping(session, mapping_id)
    _mapping_access(session, item, principal)
    action = action.upper()
    if action not in {"CONFIRM", "REJECT", "SUPERSEDE"}:
        raise DomainError(422, "invalid_mapping_action", "Unsupported mapping lifecycle action")
    if item.status != "PROPOSED":
        raise ConflictError(
            "Only a proposed mapping can be reviewed", code="invalid_mapping_transition"
        )
    if action == "REJECT" and not (reason or "").strip():
        raise DomainError(422, "review_reason_required", "A rejection reason is required")
    item.status = {"CONFIRM": "CONFIRMED", "REJECT": "REJECTED", "SUPERSEDE": "SUPERSEDED"}[action]
    item.reviewed_by_user_id = principal.user.id
    item.reviewed_at = datetime.now(UTC)
    item.review_reason = reason
    if action == "CONFIRM" and item.supersedes_mapping_id:
        superseded = _mapping(session, item.supersedes_mapping_id)
        superseded.status = "SUPERSEDED"
        record_audit_event(
            session,
            actor=principal,
            action="REQUIREMENT_MAPPING_SUPERSEDED",
            entity_type="REQUIREMENT_EVIDENCE_MAPPING",
            entity_id=str(superseded.id),
            correlation_id=correlation_id,
            after_summary={"replacement_mapping_id": str(item.id)},
        )
    record_audit_event(
        session,
        actor=principal,
        action=f"REQUIREMENT_MAPPING_{action}",
        entity_type="REQUIREMENT_EVIDENCE_MAPPING",
        entity_id=str(item.id),
        correlation_id=correlation_id,
        reason=reason,
        before_summary={"status": "PROPOSED"},
        after_summary={
            "status": item.status,
            "requirement_id": str(item.requirement_id),
            "document_version_id": str(item.document_version_id),
        },
    )
    return item
