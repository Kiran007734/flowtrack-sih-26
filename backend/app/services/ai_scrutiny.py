from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Application,
    ComplianceEvidence,
    ComplianceObligation,
    Document,
    DocumentVersion,
)
from app.permissions.access import Principal, require_institution_access, require_permission
from app.services.audit import record_audit_event


def assist_scrutiny(
    session: Session, *, application: Application, principal: Principal, correlation_id: str | None
) -> dict:
    """Deterministic, read-only fallback until an approved guidance corpus/OCR adapter exists."""
    require_permission(principal, "application.read")
    require_institution_access(principal, application.institution)
    documents = list(
        session.scalars(select(Document).where(Document.application_id == application.id))
    )
    sources = []
    for document in documents:
        version = session.scalar(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version_number.desc())
        )
        if version:
            sources.append(
                {
                    "document_id": str(document.id),
                    "document_version_id": str(version.id),
                    "filename": version.original_filename,
                    "page_or_section": None,
                    "source_kind": "submitted_evidence_metadata",
                }
            )
    obligations = list(
        session.scalars(
            select(ComplianceObligation).where(
                ComplianceObligation.application_id == application.id
            )
        )
    )
    reviewed = list(
        session.scalars(
            select(ComplianceEvidence)
            .join(ComplianceObligation)
            .where(ComplianceObligation.application_id == application.id)
        )
    )
    missing = [
        item.title
        for item in obligations
        if item.required_evidence and item.status not in {"VERIFIED", "CLOSED"}
    ]
    record_audit_event(
        session,
        actor=principal,
        action="AI_SCRUTINY_ASSIST_VIEWED",
        entity_type="APPLICATION",
        entity_id=str(application.id),
        correlation_id=correlation_id,
        after_summary={"source_count": len(sources), "fallback": True},
    )
    return {
        "mode": "DETERMINISTIC_METADATA_FALLBACK",
        "non_binding": True,
        "corpus_status": (
            "No approved versioned guidance corpus is available; "
            "no requirement citation can be established."
        ),
        "sources": sources,
        "source_backed_facts": {
            "submitted_document_count": len(sources),
            "compliance_evidence_count": len(reviewed),
            "open_required_obligations": missing,
        },
        "suggestions": [
            "Request human review of each submitted document version.",
            (
                "Resolve the listed open synthetic compliance obligations before "
                "treating their evidence as complete."
            ),
        ]
        if missing
        else [
            (
                "No open required synthetic compliance obligations were found; "
                "human review is still required."
            )
        ],
        "uncertainty": [
            (
                "No OCR text, page extraction, requirement passage, embedding retrieval, "
                "or LLM answer was used."
            ),
            (
                "This response cannot determine approval, rejection, statutory compliance, "
                "or workflow outcome."
            ),
        ],
    }
