from __future__ import annotations

from datetime import UTC, datetime
from importlib.util import find_spec
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AuthorizationError, ConflictError, DomainError, NotFoundError
from app.models import (
    DocumentVersion,
    GuidanceExtractionCorrection,
    GuidanceExtractionPage,
    GuidanceExtractionRun,
    GuidanceSourceVersion,
)
from app.permissions.access import Principal, require_permission
from app.services.audit import record_audit_event
from app.services.documents import get_document, private_storage


def _version(session: Session, version_id: UUID) -> GuidanceSourceVersion:
    item = session.get(GuidanceSourceVersion, version_id)
    if item is None:
        raise NotFoundError("The requested guidance version was not found")
    return item


def _run(session: Session, run_id: UUID) -> GuidanceExtractionRun:
    item = session.get(GuidanceExtractionRun, run_id)
    if item is None:
        raise NotFoundError("The requested extraction run was not found")
    return item


def _access_source(
    session: Session, version_id: UUID, principal: Principal
) -> GuidanceSourceVersion:
    require_permission(principal, "guidance.read")
    return _version(session, version_id)


def _access_run_document(
    session: Session, item: GuidanceExtractionRun, principal: Principal
) -> None:
    """Extraction text inherits the private document's authorization boundary."""
    get_document(session, item.document_id, principal)


def _summary(item: GuidanceExtractionRun) -> dict[str, object]:
    return {
        "id": str(item.id),
        "source_version_id": str(item.source_version_id),
        "document_id": str(item.document_id),
        "document_version_id": str(item.document_version_id),
        "attempt_number": item.attempt_number,
        "status": item.status,
        "extractor_name": item.extractor_name,
        "extractor_version": item.extractor_version,
        "failure_category": item.failure_category,
        "warnings": item.warnings,
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        "review_status": item.review_status,
        "review_reason": item.review_reason,
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
    }


def start_ingestion(
    session: Session,
    *,
    source_version_id: UUID,
    document_id: UUID,
    document_version_id: UUID,
    principal: Principal,
    correlation_id: str | None,
) -> GuidanceExtractionRun:
    require_permission(principal, "guidance.ingest")
    source = _access_source(session, source_version_id, principal)
    if source.status in {"SUPERSEDED", "ARCHIVED"}:
        raise ConflictError(
            "Archived or superseded guidance cannot be ingested", code="guidance_inactive"
        )
    document = get_document(session, document_id, principal)
    version = session.get(DocumentVersion, document_version_id)
    if version is None or version.document_id != document.id:
        raise DomainError(
            422, "invalid_document_version", "The document version does not belong to the document"
        )
    if source.original_document_version_id and source.original_document_version_id != version.id:
        raise ConflictError(
            "Guidance source versions are pinned to their original file",
            code="guidance_file_immutable",
        )
    active = session.scalar(
        select(GuidanceExtractionRun).where(
            GuidanceExtractionRun.source_version_id == source.id,
            GuidanceExtractionRun.document_version_id == version.id,
            GuidanceExtractionRun.status.in_(["QUEUED", "PROCESSING"]),
        )
    )
    if active is not None:
        return active
    attempt = (
        int(
            session.scalar(
                select(func.max(GuidanceExtractionRun.attempt_number)).where(
                    GuidanceExtractionRun.source_version_id == source.id
                )
            )
            or 0
        )
        + 1
    )
    source.original_document_id = document.id
    source.original_document_version_id = version.id
    source.ingestion_status = "QUEUED"
    item = GuidanceExtractionRun(
        id=uuid4(),
        source_version_id=source.id,
        document_id=document.id,
        document_version_id=version.id,
        attempt_number=attempt,
        status="QUEUED",
        extractor_name="pypdf+pytesseract",
        extractor_version="optional-local",
        source_file_hash=version.checksum_sha256,
        configuration={
            "max_pages": get_settings().max_ocr_page_count,
            "max_input_bytes": get_settings().max_ocr_input_bytes,
            "minimum_text_characters": get_settings().ocr_minimum_text_characters,
        },
        warnings=[],
    )
    session.add(item)
    session.flush()
    record_audit_event(
        session,
        actor=principal,
        action="GUIDANCE_INGESTION_QUEUED",
        entity_type="GUIDANCE_EXTRACTION_RUN",
        entity_id=str(item.id),
        correlation_id=correlation_id,
        after_summary={
            "source_version_id": str(source.id),
            "document_version_id": str(version.id),
            "attempt": attempt,
        },
    )
    return item


def _embedded_pdf_pages(path: Path, maximum: int) -> list[str]:
    if find_spec("pypdf") is None:
        raise RuntimeError("PDF_TEXT_EXTRACTOR_UNAVAILABLE")
    from pypdf import PdfReader

    reader = PdfReader(str(path), strict=False)
    if len(reader.pages) > maximum:
        raise DomainError(
            422, "document_page_limit", "The document exceeds the configured page limit"
        )
    return [(page.extract_text() or "").strip() for page in reader.pages]


def _configure_ocr() -> None:
    if find_spec("pytesseract") is None or find_spec("PIL") is None:
        raise RuntimeError("OCR_PYTHON_ADAPTER_UNAVAILABLE")
    import pytesseract

    configured = get_settings().ocr_executable_path
    if configured:
        if not configured.is_file():
            raise RuntimeError("OCR_EXECUTABLE_NOT_FOUND")
        pytesseract.pytesseract.tesseract_cmd = str(configured)
    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError("OCR_EXECUTABLE_NOT_FOUND") from exc


def _ocr_image(image: object) -> str:
    _configure_ocr()
    import pytesseract

    return pytesseract.image_to_string(image, timeout=get_settings().ocr_timeout_seconds).strip()


def _render_pdf_page(path: Path, page_number: int) -> object:
    if find_spec("pypdfium2") is None:
        raise RuntimeError("PDF_RENDERER_UNAVAILABLE")
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(path))
    try:
        page = document[page_number - 1]
        bitmap = page.render(scale=get_settings().ocr_render_scale)
        image = bitmap.to_pil()
        if image.width * image.height > get_settings().max_ocr_image_pixels:
            image.close()
            raise RuntimeError("OCR_IMAGE_PIXEL_LIMIT")
        return image.copy()
    finally:
        document.close()


def process_ingestion(
    session: Session,
    *,
    run_id: UUID,
    principal: Principal | None = None,
    correlation_id: str | None = None,
) -> GuidanceExtractionRun:
    item = _run(session, run_id)
    if item.status in {"EXTRACTED", "NEEDS_REVIEW", "APPROVED_FOR_USE"}:
        return item
    source = _version(session, item.source_version_id)
    version = session.get(DocumentVersion, item.document_version_id)
    if version is None or version.checksum_sha256 != item.source_file_hash:
        item.status = "FAILED"
        item.failure_category = "SOURCE_FILE_MISMATCH"
        source.ingestion_status = "FAILED"
        record_audit_event(
            session,
            actor=principal,
            action="GUIDANCE_INGESTION_PROCESSED",
            entity_type="GUIDANCE_EXTRACTION_RUN",
            entity_id=str(item.id),
            correlation_id=correlation_id,
            outcome="FAILURE",
            after_summary={"status": item.status, "failure_category": item.failure_category},
        )
        return item
    if version.size_bytes > get_settings().max_ocr_input_bytes:
        item.status = "FAILED"
        item.failure_category = "OCR_INPUT_SIZE_LIMIT"
        item.warnings = ["The source document exceeds the configured OCR input size limit."]
        source.ingestion_status = "FAILED"
        item.completed_at = datetime.now(UTC)
        record_audit_event(
            session,
            actor=principal,
            action="GUIDANCE_INGESTION_PROCESSED",
            entity_type="GUIDANCE_EXTRACTION_RUN",
            entity_id=str(item.id),
            correlation_id=correlation_id,
            outcome="FAILURE",
            after_summary={"status": item.status, "failure_category": item.failure_category},
        )
        return item
    item.status = "PROCESSING"
    item.started_at = datetime.now(UTC)
    source.ingestion_status = "PROCESSING"
    try:
        storage = private_storage()
        if storage.checksum(version.storage_key) != item.source_file_hash:
            raise RuntimeError("SOURCE_FILE_MISMATCH")
        path = storage.retrieve_path(version.storage_key)
        pages: list[str]
        methods: list[str]
        if version.mime_type == "application/pdf":
            pages = _embedded_pdf_pages(path, get_settings().max_ocr_page_count)
            methods = []
            for number, text in enumerate(pages, start=1):
                if len(text) >= get_settings().ocr_minimum_text_characters:
                    methods.append("EMBEDDED_TEXT")
                    continue
                image = _render_pdf_page(path, number)
                try:
                    pages[number - 1] = _ocr_image(image)
                finally:
                    image.close()
                methods.append("OCR_PDF_RENDER")
        elif version.mime_type in {"image/png", "image/jpeg"}:
            from PIL import Image

            with Image.open(path) as image:
                image.load()
                if image.width * image.height > get_settings().max_ocr_image_pixels:
                    raise RuntimeError("OCR_IMAGE_PIXEL_LIMIT")
                pages = [_ocr_image(image)]
                methods = ["OCR_IMAGE"]
        else:
            raise DomainError(422, "unsupported_ingestion_type", "This format cannot be ingested")
        if not pages:
            raise RuntimeError("EMPTY_DOCUMENT")
        for number, text in enumerate(pages, start=1):
            warnings = []
            if len(text) < get_settings().ocr_minimum_text_characters:
                warnings.append("LOW_TEXT_COVERAGE")
            if not text:
                warnings.append("BLANK_OR_UNREADABLE_PAGE")
            session.add(
                GuidanceExtractionPage(
                    id=uuid4(),
                    run_id=item.id,
                    page_number=number,
                    raw_text=text,
                    method=methods[number - 1],
                    confidence=None,
                    quality_metadata={
                        "character_count": len(text),
                        "minimum_text_characters": get_settings().ocr_minimum_text_characters,
                    },
                    warnings=warnings,
                )
            )
            item.warnings.extend([f"PAGE_{number}:{warning}" for warning in warnings])
        item.status = "NEEDS_REVIEW"
        item.review_status = "PENDING"
        source.ingestion_status = "NEEDS_REVIEW"
        item.completed_at = datetime.now(UTC)
    except DomainError:
        raise
    except Exception as exc:
        item.status = "FAILED"
        item.failure_category = str(exc)[:96]
        item.warnings = ["Extraction failed; no text is available."]
        source.ingestion_status = "FAILED"
        item.completed_at = datetime.now(UTC)
    record_audit_event(
        session,
        actor=principal,
        action="GUIDANCE_INGESTION_PROCESSED",
        entity_type="GUIDANCE_EXTRACTION_RUN",
        entity_id=str(item.id),
        correlation_id=correlation_id,
        outcome="SUCCESS" if item.status == "NEEDS_REVIEW" else "FAILURE",
        after_summary={
            "status": item.status,
            "failure_category": item.failure_category,
            "warning_count": len(item.warnings),
        },
    )
    return item


def list_runs(
    session: Session, *, source_version_id: UUID, principal: Principal
) -> list[dict[str, object]]:
    _access_source(session, source_version_id, principal)
    visible: list[dict[str, object]] = []
    for item in session.scalars(
        select(GuidanceExtractionRun)
        .where(GuidanceExtractionRun.source_version_id == source_version_id)
        .order_by(GuidanceExtractionRun.attempt_number.desc())
    ):
        try:
            _access_run_document(session, item, principal)
        except AuthorizationError:
            continue
        visible.append(_summary(item))
    return visible


def run_detail(session: Session, *, run_id: UUID, principal: Principal) -> dict[str, object]:
    item = _run(session, run_id)
    _access_source(session, item.source_version_id, principal)
    _access_run_document(session, item, principal)
    pages = session.scalars(
        select(GuidanceExtractionPage)
        .where(GuidanceExtractionPage.run_id == item.id)
        .order_by(GuidanceExtractionPage.page_number)
    )
    corrections = session.scalars(
        select(GuidanceExtractionCorrection)
        .join(
            GuidanceExtractionPage,
            GuidanceExtractionCorrection.page_id == GuidanceExtractionPage.id,
        )
        .where(GuidanceExtractionPage.run_id == item.id)
        .order_by(
            GuidanceExtractionCorrection.page_id, GuidanceExtractionCorrection.revision_number
        )
    )
    corrections_by_page: dict[UUID, list[dict[str, object]]] = {}
    for correction in corrections:
        corrections_by_page.setdefault(correction.page_id, []).append(
            {
                "revision_number": correction.revision_number,
                "corrected_text": correction.corrected_text,
                "reason": correction.reason,
                "corrected_at": correction.created_at.isoformat(),
            }
        )
    return {
        **_summary(item),
        "pages": [
            {
                "id": str(page.id),
                "page_number": page.page_number,
                "raw_text": page.raw_text,
                "corrected_text": page.corrected_text,
                "method": page.method,
                "confidence": page.confidence,
                "quality_metadata": page.quality_metadata,
                "warnings": page.warnings,
                "corrected_at": page.corrected_at.isoformat() if page.corrected_at else None,
                "corrections": corrections_by_page.get(page.id, []),
            }
            for page in pages
        ],
    }


def review_run(
    session: Session,
    *,
    run_id: UUID,
    action: str,
    reason: str | None,
    principal: Principal,
    correlation_id: str | None,
) -> GuidanceExtractionRun:
    require_permission(principal, "guidance.extract.review")
    item = _run(session, run_id)
    source = _access_source(session, item.source_version_id, principal)
    _access_run_document(session, item, principal)
    if item.status != "NEEDS_REVIEW":
        raise ConflictError(
            "Only extracted runs awaiting review may be reviewed",
            code="invalid_extraction_transition",
        )
    if action == "reject" and not (reason or "").strip():
        raise DomainError(422, "review_reason_required", "A rejection reason is required")
    item.review_status = "APPROVED" if action == "approve" else "REJECTED"
    item.status = "APPROVED_FOR_USE" if action == "approve" else "REJECTED"
    item.review_reason = reason
    item.reviewed_by_user_id = principal.user.id
    item.reviewed_at = datetime.now(UTC)
    source.ingestion_status = item.status
    record_audit_event(
        session,
        actor=principal,
        action=f"GUIDANCE_EXTRACTION_{action.upper()}",
        entity_type="GUIDANCE_EXTRACTION_RUN",
        entity_id=str(item.id),
        correlation_id=correlation_id,
        reason=reason,
        after_summary={"status": item.status},
    )
    return item


def correct_page(
    session: Session,
    *,
    page_id: UUID,
    corrected_text: str,
    reason: str,
    principal: Principal,
    correlation_id: str | None,
) -> GuidanceExtractionPage:
    require_permission(principal, "guidance.extract.review")
    page = session.get(GuidanceExtractionPage, page_id)
    if page is None:
        raise NotFoundError("The requested extraction page was not found")
    run = _run(session, page.run_id)
    _access_source(session, run.source_version_id, principal)
    _access_run_document(session, run, principal)
    if run.status not in {"NEEDS_REVIEW", "REJECTED"}:
        raise ConflictError(
            "Only reviewable extraction pages may be corrected", code="invalid_correction_state"
        )
    next_revision = (
        int(
            session.scalar(
                select(func.max(GuidanceExtractionCorrection.revision_number)).where(
                    GuidanceExtractionCorrection.page_id == page.id
                )
            )
            or 0
        )
        + 1
    )
    session.add(
        GuidanceExtractionCorrection(
            id=uuid4(),
            page_id=page.id,
            revision_number=next_revision,
            corrected_text=corrected_text,
            reason=reason,
            corrected_by_user_id=principal.user.id,
        )
    )
    page.corrected_text = corrected_text
    page.corrected_by_user_id = principal.user.id
    page.corrected_at = datetime.now(UTC)
    record_audit_event(
        session,
        actor=principal,
        action="GUIDANCE_EXTRACTION_PAGE_CORRECTED",
        entity_type="GUIDANCE_EXTRACTION_PAGE",
        entity_id=str(page.id),
        correlation_id=correlation_id,
        reason=reason,
        after_summary={
            "run_id": str(run.id),
            "page_number": page.page_number,
            "revision_number": next_revision,
        },
    )
    return page
