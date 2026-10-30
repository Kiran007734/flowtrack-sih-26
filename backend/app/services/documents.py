from __future__ import annotations

import re
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Final
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import DomainError, NotFoundError
from app.models import Application, Document, DocumentVersion
from app.permissions.access import Principal, require_institution_access, require_permission
from app.services.audit import record_audit_event
from app.storage import LocalPrivateStorage, StorageError

_EXTENSIONS: Final[dict[str, set[str]]] = {
    "application/pdf": {".pdf"},
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
    "text/plain": {".txt"},
}


def private_storage(settings: Settings | None = None) -> LocalPrivateStorage:
    return LocalPrivateStorage((settings or get_settings()).private_storage_root)


def safe_display_filename(filename: str | None) -> str:
    raw = (filename or "upload").replace("\\", "/").split("/")[-1]
    raw = re.sub(r"[\x00-\x1f<>:\\|?*]", "_", raw).strip(". ")
    return (raw or "upload")[:255]


def detect_mime_type(content: bytes) -> str | None:
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if b"\x00" not in content:
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            return None
        return "text/plain"
    return None


def validate_upload(
    *,
    content: bytes,
    original_filename: str | None,
    supplied_mime_type: str | None,
    settings: Settings,
) -> tuple[str, str, str]:
    if not content:
        raise DomainError(422, "empty_document", "The uploaded document is empty")
    if len(content) > settings.max_upload_size_bytes:
        raise DomainError(
            422, "document_too_large", "The uploaded document exceeds the configured size limit"
        )
    safe_name = safe_display_filename(original_filename)
    detected = detect_mime_type(content)
    if detected is None or detected not in settings.allowed_document_types:
        raise DomainError(422, "unsupported_document_type", "This document type is not supported")
    extension = PurePosixPath(safe_name).suffix.lower()
    if extension not in _EXTENSIONS.get(detected, set()):
        raise DomainError(
            422, "invalid_document_extension", "The document extension does not match its content"
        )
    claimed = (supplied_mime_type or "").lower().split(";", 1)[0].strip()
    if claimed and claimed not in {"application/octet-stream", detected}:
        raise DomainError(
            422, "mime_type_mismatch", "The supplied document type does not match its content"
        )
    return safe_name, detected, sha256(content).hexdigest()


def _application_for_upload(
    session: Session, application_id: UUID, principal: Principal
) -> Application:
    application = session.get(Application, application_id)
    if application is None:
        raise NotFoundError("The requested application was not found")
    require_permission(principal, "document.write")
    require_institution_access(principal, application.institution)
    return application


def upload_document(
    session: Session,
    *,
    principal: Principal,
    application_id: UUID,
    classification: str,
    original_filename: str | None,
    supplied_mime_type: str | None,
    content: bytes,
    correlation_id: str | None,
    settings: Settings | None = None,
) -> Document:
    settings = settings or get_settings()
    application = _application_for_upload(session, application_id, principal)
    safe_name, mime_type, checksum = validate_upload(
        content=content,
        original_filename=original_filename,
        supplied_mime_type=supplied_mime_type,
        settings=settings,
    )
    document = Document(
        id=uuid4(),
        institution_id=application.institution_id,
        application_id=application.id,
        classification=(classification or "INTERNAL").strip().upper()[:64],
        current_version_number=1,
        status="AVAILABLE",
    )
    storage_key = f"documents/{application.institution_id}/{document.id}/1-{uuid4().hex}"
    storage = private_storage(settings)
    try:
        storage.store(storage_key, content)
        session.add(document)
        session.add(
            DocumentVersion(
                document_id=document.id,
                version_number=1,
                original_filename=safe_name,
                storage_key=storage_key,
                mime_type=mime_type,
                size_bytes=len(content),
                checksum_sha256=checksum,
                uploaded_by_user_id=principal.user.id,
                processing_status="NOT_REQUESTED",
            )
        )
        session.flush()
    except Exception:
        storage.delete(storage_key)
        raise
    record_audit_event(
        session,
        actor=principal,
        action="DOCUMENT_UPLOADED",
        entity_type="DOCUMENT",
        entity_id=str(document.id),
        correlation_id=correlation_id,
        after_summary={
            "application_id": str(application.id),
            "classification": document.classification,
            "mime_type": mime_type,
            "size_bytes": len(content),
            "checksum_sha256": checksum,
        },
    )
    return document


def get_document(session: Session, document_id: UUID, principal: Principal) -> Document:
    document = session.get(Document, document_id)
    if document is None:
        raise NotFoundError("The requested document was not found")
    require_permission(principal, "document.read")
    application = (
        session.get(Application, document.application_id) if document.application_id else None
    )
    if application is not None:
        require_institution_access(principal, application.institution)
    else:
        from app.models import Institution

        institution = session.get(Institution, document.institution_id)
        if institution is None:
            raise NotFoundError("The requested document was not found")
        require_institution_access(principal, institution)
    return document


def document_versions(session: Session, document: Document) -> list[DocumentVersion]:
    return list(
        session.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version_number.desc())
        )
    )


def upload_document_version(
    session: Session,
    *,
    principal: Principal,
    document_id: UUID,
    original_filename: str | None,
    supplied_mime_type: str | None,
    content: bytes,
    correlation_id: str | None,
    settings: Settings | None = None,
) -> Document:
    settings = settings or get_settings()
    document = get_document(session, document_id, principal)
    require_permission(principal, "document.write")
    safe_name, mime_type, checksum = validate_upload(
        content=content,
        original_filename=original_filename,
        supplied_mime_type=supplied_mime_type,
        settings=settings,
    )
    next_version = document.current_version_number + 1
    storage_key = f"documents/{document.institution_id}/{document.id}/{next_version}-{uuid4().hex}"
    storage = private_storage(settings)
    try:
        storage.store(storage_key, content)
        document.current_version_number = next_version
        session.add(
            DocumentVersion(
                document_id=document.id,
                version_number=next_version,
                original_filename=safe_name,
                storage_key=storage_key,
                mime_type=mime_type,
                size_bytes=len(content),
                checksum_sha256=checksum,
                uploaded_by_user_id=principal.user.id,
                processing_status="NOT_REQUESTED",
            )
        )
        session.flush()
    except Exception:
        storage.delete(storage_key)
        raise
    record_audit_event(
        session,
        actor=principal,
        action="DOCUMENT_VERSION_UPLOADED",
        entity_type="DOCUMENT",
        entity_id=str(document.id),
        correlation_id=correlation_id,
        after_summary={"version_number": next_version, "checksum_sha256": checksum},
    )
    return document


def current_document_version(session: Session, document: Document) -> DocumentVersion:
    version = session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_number == document.current_version_number,
        )
    )
    if version is None:
        raise NotFoundError("The requested document version was not found")
    return version


def private_document_path(
    session: Session,
    *,
    document_id: UUID,
    principal: Principal,
    correlation_id: str | None,
    settings: Settings | None = None,
) -> tuple[DocumentVersion, object]:
    document = get_document(session, document_id, principal)
    require_permission(principal, "document.download")
    version = current_document_version(session, document)
    storage = private_storage(settings)
    try:
        path = storage.retrieve_path(version.storage_key)
        if storage.checksum(version.storage_key) != version.checksum_sha256:
            raise StorageError("Document checksum verification failed")
    except StorageError as exc:
        document.status = "UNAVAILABLE"
        raise NotFoundError("The requested document is unavailable") from exc
    record_audit_event(
        session,
        actor=principal,
        action="DOCUMENT_DOWNLOADED",
        entity_type="DOCUMENT",
        entity_id=str(document.id),
        correlation_id=correlation_id,
        after_summary={"version_number": version.version_number},
    )
    return version, path
