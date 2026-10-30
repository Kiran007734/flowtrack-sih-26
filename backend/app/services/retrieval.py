# ruff: noqa: E501
from __future__ import annotations

import re
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, DomainError
from app.models import (
    GuidanceExtractionPage,
    GuidanceExtractionRun,
    GuidancePassage,
    GuidanceSource,
    GuidanceSourceVersion,
)
from app.permissions.access import Principal, require_permission
from app.services.audit import record_audit_event
from app.services.documents import get_document

CHUNK_SIZE = 900
MAX_QUERY_LENGTH = 500


def _eligible(
    session: Session, version_id: UUID
) -> tuple[GuidanceSource, GuidanceSourceVersion, GuidanceExtractionRun]:
    version = session.get(GuidanceSourceVersion, version_id)
    if not version or version.status != "APPROVED":
        raise ConflictError(
            "Only approved guidance versions may be indexed", code="guidance_not_approved"
        )
    source = session.get(GuidanceSource, version.source_id)
    run = session.scalar(
        select(GuidanceExtractionRun)
        .where(
            GuidanceExtractionRun.source_version_id == version.id,
            GuidanceExtractionRun.status == "APPROVED_FOR_USE",
        )
        .order_by(GuidanceExtractionRun.completed_at.desc())
    )
    if not source or not run:
        raise ConflictError(
            "An approved extraction is required before indexing", code="extraction_not_approved"
        )
    return source, version, run


def _chunks(text: str) -> list[str]:
    words = text.split()
    return [
        " ".join(words[i : i + CHUNK_SIZE])
        for i in range(0, len(words), CHUNK_SIZE)
        if words[i : i + CHUNK_SIZE]
    ]


def index_version(
    session: Session, *, version_id: UUID, principal: Principal, correlation_id: str | None
) -> dict[str, object]:
    require_permission(principal, "guidance.ingest")
    source, version, run = _eligible(session, version_id)
    get_document(session, run.document_id, principal)
    existing = list(
        session.scalars(
            select(GuidancePassage).where(
                GuidancePassage.source_version_id == version.id, GuidancePassage.is_active.is_(True)
            )
        )
    )
    for passage in existing:
        passage.is_active = False
        passage.superseded_at = datetime.now(UTC)
    index_version_number = max((p.index_version for p in existing), default=0) + 1
    count = 0
    for page in session.scalars(
        select(GuidanceExtractionPage)
        .where(GuidanceExtractionPage.run_id == run.id)
        .order_by(GuidanceExtractionPage.page_number)
    ):
        text = page.corrected_text or page.raw_text
        if not text.strip() or "BLANK_OR_UNREADABLE_PAGE" in page.warnings:
            continue
        for chunk_number, chunk in enumerate(_chunks(text), start=1):
            session.add(
                GuidancePassage(
                    id=uuid4(),
                    source_id=source.id,
                    source_version_id=version.id,
                    extraction_run_id=run.id,
                    extraction_page_id=page.id,
                    document_id=run.document_id,
                    document_version_id=run.document_version_id,
                    page_number=page.page_number,
                    chunk_number=chunk_number,
                    text=chunk,
                    content_hash=sha256(chunk.encode()).hexdigest(),
                    chunking_strategy="word-window-900-v1",
                    index_version=index_version_number,
                    embedding_model=None,
                    embedding_status="NOT_AVAILABLE",
                    provenance={
                        "verification_status": version.verification_status,
                        "run_status": run.status,
                    },
                    is_active=True,
                )
            )
            count += 1
    if not count:
        raise DomainError(
            422, "no_indexable_passages", "The approved extraction has no usable pages"
        )
    record_audit_event(
        session,
        actor=principal,
        action="GUIDANCE_VERSION_INDEXED",
        entity_type="GUIDANCE_SOURCE_VERSION",
        entity_id=str(version.id),
        correlation_id=correlation_id,
        after_summary={
            "passage_count": count,
            "index_version": index_version_number,
            "embedding_mode": "UNAVAILABLE_LEXICAL_FALLBACK",
        },
    )
    return {
        "source_version_id": str(version.id),
        "passage_count": count,
        "index_version": index_version_number,
        "mode": "LEXICAL_FALLBACK_NO_EMBEDDING_MODEL",
    }


def search(
    session: Session, *, question: str, principal: Principal, limit: int = 10
) -> list[dict[str, object]]:
    require_permission(principal, "guidance.read")
    if not question.strip() or len(question) > MAX_QUERY_LENGTH:
        raise DomainError(422, "invalid_query", "Question must be between 1 and 500 characters")
    terms = {token.lower() for token in re.findall(r"[A-Za-z0-9]{3,}", question)}
    scored: list[tuple[int, GuidancePassage]] = []
    for passage in session.scalars(
        select(GuidancePassage).where(GuidancePassage.is_active.is_(True))
    ):
        get_document(session, passage.document_id, principal)
        score = sum(term in passage.text.lower() for term in terms)
        if score:
            scored.append((score, passage))
    scored.sort(key=lambda item: (-item[0], str(item[1].id)))
    return [
        {
            "passage_id": str(p.id),
            "text": p.text,
            "source_version_id": str(p.source_version_id),
            "page_number": p.page_number,
            "verification_status": p.provenance.get("verification_status"),
            "relevance_method": "LEXICAL_FALLBACK",
            "lexical_score": score,
            "semantic_score": None,
            "citation": {"page": p.page_number, "document_version_id": str(p.document_version_id)},
        }
        for score, p in scored[: max(1, min(limit, 20))]
    ]
