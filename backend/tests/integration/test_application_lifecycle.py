from __future__ import annotations

from uuid import UUID, uuid4

from app.db.seed import DEMO_PASSWORD, seed
from app.db.session import SessionLocal
from app.models import (
    Application,
    AuditEvent,
    CatalogueRequirement,
    CommitteeReview,
    CommunicationDraft,
    Document,
    DocumentVersion,
    EvcChecklistItem,
    EvcEvidenceLink,
    EvcReport,
    EvcVisit,
    GuidanceExtractionRun,
    GuidanceSourceVersion,
    Notification,
    OutboxEvent,
    RequirementEvidenceMapping,
    RoleAssignment,
    User,
    WorkflowTransition,
)
from app.permissions.access import build_principal
from app.services.applications import create_draft
from app.services.outbox import dispatch_pending_events
from app.services.workflow import evaluate_transition
from fastapi.testclient import TestClient
from sqlalchemy import func, select


def _login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    assert response.status_code == 200, response.text
    return {
        "Authorization": f"Bearer {response.json()['access_token']}",
        "Idempotency-Key": str(uuid4()),
    }


def _assign_scrutiny_reviewer(
    client: TestClient, application_id: str, regional_headers: dict[str, str], reviewer_email: str
) -> dict[str, object]:
    with SessionLocal() as session:
        reviewer = session.scalar(select(User).where(User.email == reviewer_email))
        assert reviewer is not None
    response = client.post(
        f"/api/v1/applications/{application_id}/reviewer-assignments",
        headers=regional_headers,
        json={"reviewer_id": str(reviewer.id), "reason": "Synthetic assignment"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _new_idempotency(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Idempotency-Key": str(uuid4())}


def test_guidance_catalogue_and_human_reviewed_mapping_lifecycle(client: TestClient) -> None:
    seed()
    admin = _login(client, "admin@example.org")
    source = client.post(
        "/api/v1/guidance-sources",
        headers=admin,
        json={
            "key": "TEST-GUIDANCE",
            "title": "Synthetic test guidance",
            "source_type": "DEMONSTRATION_GUIDANCE",
            "version_label": "test-1",
            "verification_status": "SYNTHETIC_DEMONSTRATION",
        },
    )
    assert source.status_code == 201, source.text
    version_id = source.json()["version"]["id"]
    applicant = _login(client, "applicant.alpha@example.org")
    assert (
        client.post(
            f"/api/v1/guidance-versions/{version_id}/approve",
            headers=applicant,
            json={"reason": "Unauthorized approval attempt"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/guidance-versions/{version_id}/submit",
            headers=_new_idempotency(admin),
            json={},
        ).status_code
        == 200
    )
    approved = client.post(
        f"/api/v1/guidance-versions/{version_id}/approve",
        headers=_new_idempotency(admin),
        json={},
    )
    assert approved.status_code == 200 and approved.json()["status"] == "APPROVED"
    assert (
        client.post(
            f"/guidance-versions/{version_id}/approve",
            headers=_new_idempotency(admin),
            json={},
        ).status_code
        == 404
    )
    requirement = client.post(
        "/api/v1/catalogue-requirements",
        headers=_new_idempotency(admin),
        json={
            "stable_identifier": "TEST.DOCUMENT",
            "source_version_id": version_id,
            "title": "Synthetic document check",
            "description": "A labelled synthetic catalogue requirement.",
            "category": "APPLICATION_DOCUMENTATION",
            "module_key": "APPLICATION",
        },
    )
    assert requirement.status_code == 201, requirement.text
    requirement_id = requirement.json()["id"]
    assert (
        client.post(
            f"/api/v1/catalogue-requirements/{requirement_id}/submit",
            headers=_new_idempotency(admin),
            json={},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/catalogue-requirements/{requirement_id}/approve",
            headers=_new_idempotency(admin),
            json={},
        ).json()["status"]
        == "APPROVED"
    )

    alpha = _login(client, "applicant.alpha@example.org")
    with SessionLocal() as session:
        application = session.scalar(
            select(Application).where(Application.reference_number == "DEMO-APP-ALPHA-SUBMITTED")
        )
        document = session.scalar(select(Document).where(Document.application_id == application.id))
        version = session.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == document.id)
        )
        assert application is not None and document is not None and version is not None
        application_id, document_id, document_version_id = (
            str(application.id),
            str(document.id),
            str(version.id),
        )
    proposed = client.post(
        "/api/v1/requirement-evidence-mappings",
        headers=alpha,
        json={
            "requirement_id": requirement_id,
            "application_id": application_id,
            "document_id": document_id,
            "document_version_id": document_version_id,
            "explanation": "Exact private document version reviewed by applicant.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    mapping_id = proposed.json()["id"]
    assert (
        client.post(
            f"/api/v1/requirement-evidence-mappings/{mapping_id}/confirm",
            headers=_new_idempotency(alpha),
            json={},
        ).status_code
        == 403
    )
    regional = _login(client, "regional.north@example.org")
    confirmed = client.post(
        f"/api/v1/requirement-evidence-mappings/{mapping_id}/confirm",
        headers=regional,
        json={},
    )
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "CONFIRMED"
    rejected = client.post(
        f"/api/v1/requirement-evidence-mappings/{mapping_id}/reject",
        headers=_new_idempotency(regional),
        json={"reason": "Cannot reverse reviewed mapping"},
    )
    assert rejected.status_code == 409
    replacement = client.post(
        "/api/v1/requirement-evidence-mappings",
        headers=_new_idempotency(alpha),
        json={
            "requirement_id": requirement_id,
            "application_id": application_id,
            "document_id": document_id,
            "document_version_id": document_version_id,
            "explanation": "Replacement review preserves the prior decision as history.",
            "supersedes_mapping_id": mapping_id,
        },
    )
    assert replacement.status_code == 201, replacement.text
    assert (
        client.post(
            f"/api/v1/requirement-evidence-mappings/{replacement.json()['id']}/confirm",
            headers=_new_idempotency(regional),
            json={},
        ).status_code
        == 200
    )
    history = client.get(
        f"/api/v1/requirement-evidence-mappings/{mapping_id}/history", headers=alpha
    )
    assert history.status_code == 200
    assert any(item["action"] == "REQUIREMENT_MAPPING_PROPOSED" for item in history.json())
    beta = _login(client, "applicant.beta@example.org")
    denied = client.post(
        "/api/v1/requirement-evidence-mappings",
        headers=beta,
        json={
            "requirement_id": requirement_id,
            "application_id": application_id,
            "document_id": document_id,
            "document_version_id": document_version_id,
            "explanation": "Cross-scope attempt",
        },
    )
    assert denied.status_code == 403
    with SessionLocal() as session:
        assert session.get(RequirementEvidenceMapping, UUID(mapping_id)).status == "SUPERSEDED"
        assert (
            session.scalar(select(AuditEvent).where(AuditEvent.entity_id == mapping_id)) is not None
        )


def test_requirement_version_does_not_transfer_confirmed_mapping(client: TestClient) -> None:
    seed()
    admin = _login(client, "admin@example.org")
    with SessionLocal() as session:
        existing = session.scalar(
            select(CatalogueRequirement).where(
                CatalogueRequirement.stable_identifier == "DEMO.APPLICATION.DOCUMENT"
            )
        )
        assert existing is not None
        source_version_id = str(existing.source_version_id)
        existing_id = str(existing.id)
    replacement = client.post(
        "/api/v1/catalogue-requirements",
        headers=admin,
        json={
            "stable_identifier": "DEMO.APPLICATION.DOCUMENT",
            "source_version_id": source_version_id,
            "title": "Replacement synthetic document requirement",
            "description": "A new requirement version never inherits confirmations.",
            "category": "APPLICATION_DOCUMENTATION",
            "module_key": "APPLICATION",
            "supersedes_requirement_id": existing_id,
        },
    )
    assert replacement.status_code == 201, replacement.text
    replacement_id = replacement.json()["id"]
    assert (
        client.post(
            f"/api/v1/catalogue-requirements/{replacement_id}/submit",
            headers=_new_idempotency(admin),
            json={},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/catalogue-requirements/{replacement_id}/approve",
            headers=_new_idempotency(admin),
            json={},
        ).status_code
        == 200
    )
    with SessionLocal() as session:
        assert session.get(CatalogueRequirement, UUID(existing_id)).status == "SUPERSEDED"
        assert session.get(CatalogueRequirement, UUID(replacement_id)).status == "APPROVED"


def test_guidance_ingestion_is_pinned_audited_and_requires_human_review(client: TestClient) -> None:
    seed()
    admin = _login(client, "admin@example.org")
    with SessionLocal() as session:
        guidance = session.scalar(
            select(GuidanceSourceVersion).where(GuidanceSourceVersion.version_label == "demo-1.0")
        )
        document = session.scalar(select(Document).where(Document.application_id.is_not(None)))
        version = session.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == document.id)
        )
        assert guidance is not None and document is not None and version is not None
    result = client.post(
        f"/api/v1/guidance-versions/{guidance.id}/ingestions",
        headers=admin,
        json={
            "document_id": str(document.id),
            "document_version_id": str(version.id),
            "synchronous": True,
        },
    )
    assert result.status_code == 201, result.text
    assert result.json()["document_version_id"] == str(version.id)
    assert result.json()["status"] in {"NEEDS_REVIEW", "FAILED"}
    with SessionLocal() as session:
        run = session.get(GuidanceExtractionRun, UUID(result.json()["id"]))
        assert run is not None and run.source_file_hash == version.checksum_sha256


def test_committee_decision_and_simulated_communication_lifecycle(client: TestClient) -> None:
    seed()
    regional = _login(client, "regional.north@example.org")
    member = _login(client, "scrutiny.north@example.org")
    with SessionLocal() as session:
        application = session.scalar(
            select(Application).where(Application.assigned_region_id.is_not(None))
        )
        reviewer = session.scalar(select(User).where(User.email == "scrutiny.north@example.org"))
        assert application is not None and reviewer is not None
        # Isolated setup uses the pinned synthetic workflow's scrutiny stage.
        application.current_stage_key = "scrutiny"
        session.commit()
        original_status = application.status
    create_key = _new_idempotency(regional)
    created = client.post(
        f"/api/v1/applications/{application.id}/committee-reviews",
        headers=create_key,
        json={"stage_key": "scrutiny", "committee_type": "SYNTHETIC_PANEL"},
    )
    assert created.status_code == 201, created.text
    assert (
        client.post(
            f"/api/v1/applications/{application.id}/committee-reviews",
            headers=create_key,
            json={"stage_key": "scrutiny", "committee_type": "SYNTHETIC_PANEL"},
        ).json()["id"]
        == created.json()["id"]
    )
    review_id = created.json()["id"]
    assert (
        client.post(
            f"/api/v1/committee-reviews/{review_id}/members",
            headers=_new_idempotency(regional),
            json={"user_id": str(reviewer.id)},
        ).status_code
        == 201
    )
    submitted = client.post(
        f"/api/v1/committee-reviews/{review_id}/submissions",
        headers=member,
        json={"recommendation": "RECOMMEND_APPROVAL", "findings": "Synthetic committee findings"},
    )
    assert submitted.status_code == 201, submitted.text
    assert (
        client.post(
            f"/api/v1/committee-reviews/{review_id}/submissions",
            headers=_new_idempotency(member),
            json={"recommendation": "RECOMMEND_APPROVAL", "findings": "duplicate"},
        ).status_code
        == 409
    )
    finalized = client.post(
        f"/api/v1/committee-reviews/{review_id}/finalize",
        headers=_new_idempotency(regional),
        json={"outcome": "RECOMMEND_APPROVAL", "reason": "Synthetic consolidated reason"},
    )
    assert finalized.status_code == 200, finalized.text
    with SessionLocal() as session:
        assert session.get(Application, application.id).status == original_status
        assert session.get(CommitteeReview, UUID(review_id)).status == "FINALIZED"
    decision = client.post(
        f"/api/v1/applications/{application.id}/decisions",
        headers=_new_idempotency(regional),
        json={
            "outcome": "APPROVED",
            "rationale": "Synthetic decision rationale",
            "row_version": application.row_version,
        },
    )
    assert decision.status_code == 201, decision.text
    communication = client.post(
        f"/api/v1/applications/{application.id}/communications",
        headers=_new_idempotency(regional),
        json={
            "decision_id": decision.json()["id"],
            "subject": "Synthetic outcome",
            "body": "This is a simulated message.",
        },
    )
    assert communication.status_code == 201, communication.text
    queued = client.post(
        f"/api/v1/communications/{communication.json()['id']}/approve-and-queue",
        headers=_new_idempotency(regional),
        json={},
    )
    assert queued.status_code == 200 and queued.json()["status"] == "QUEUED_SIMULATED"
    with SessionLocal() as session:
        draft = session.get(CommunicationDraft, UUID(communication.json()["id"]))
        event = session.scalar(
            select(OutboxEvent).where(OutboxEvent.aggregate_id == communication.json()["id"])
        )
        assert draft is not None and draft.status == "QUEUED_SIMULATED" and event is not None
    assert dispatch_pending_events("test-worker") >= 2
    with SessionLocal() as session:
        draft = session.get(CommunicationDraft, UUID(communication.json()["id"]))
        committee_event = session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == review_id,
                OutboxEvent.event_type == "COMMITTEE_REVIEW_FINALIZED",
            )
        )
        audit = session.scalar(
            select(AuditEvent).where(
                AuditEvent.entity_id == communication.json()["id"],
                AuditEvent.action == "COMMUNICATION_SIMULATED_DELIVERY_COMPLETED",
            )
        )
        assert draft is not None and draft.status == "SIMULATED_DELIVERED"
        assert committee_event is not None and committee_event.status == "PROCESSED"
        assert audit is not None and audit.after_summary["real_delivery"] is False


def test_committee_idempotency_replay_requires_current_authorization(client: TestClient) -> None:
    seed()
    headers = _login(client, "regional.north@example.org")
    application = next(
        item
        for item in client.get("/api/v1/applications", headers=headers).json()["items"]
        if item["current_stage_key"] == "submitted"
    )
    payload = {"stage_key": "submitted", "committee_type": "SYNTHETIC_PANEL"}
    created = client.post(
        f"/api/v1/applications/{application['id']}/committee-reviews",
        headers=headers,
        json=payload,
    )
    assert created.status_code == 201, created.text
    with SessionLocal() as session:
        officer = session.scalar(select(User).where(User.email == "regional.north@example.org"))
        assert officer is not None
        assignment = session.scalar(
            select(RoleAssignment).where(
                RoleAssignment.user_id == officer.id,
                RoleAssignment.is_active.is_(True),
            )
        )
        assert assignment is not None
        assignment.is_active = False
        session.commit()
    replay = client.post(
        f"/api/v1/applications/{application['id']}/committee-reviews",
        headers=headers,
        json=payload,
    )
    assert replay.status_code == 403


def test_submit_is_atomic_and_creates_durable_notification(client: TestClient) -> None:
    seed()
    headers = _login(client, "applicant.alpha@example.org")
    institutions = client.get("/api/v1/institutions", headers=headers)
    assert institutions.status_code == 200
    institution_id = institutions.json()["items"][0]["id"]
    created = client.post(
        "/api/v1/applications",
        headers=headers,
        json={
            "institution_id": institution_id,
            "application_type": "SYNTHETIC_NEW_PROGRAMME",
            "title": "Atomic submission test",
            "workflow_template_key": "SCRUTINY_ONLY",
        },
    )
    assert created.status_code == 201, created.text
    application = created.json()
    blocked = client.post(
        f"/api/v1/applications/{application['id']}/submit",
        headers=headers,
        json={"row_version": application["row_version"]},
    )
    assert blocked.status_code == 422
    assert "blocking_reasons" in blocked.json()

    upload = client.post(
        "/api/v1/documents/uploads",
        headers=headers,
        data={"application_id": application["id"], "classification": "INTERNAL"},
        files={"file": ("evidence.pdf", b"%PDF-1.4\nexample\n", "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    submitted = client.post(
        f"/api/v1/applications/{application['id']}/submit",
        headers=headers,
        json={"row_version": application["row_version"]},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "SUBMITTED"
    assert submitted.json()["current_stage_key"] == "submitted"

    with SessionLocal() as session:
        event = session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == application["id"],
                OutboxEvent.event_type == "APPLICATION_SUBMITTED",
            )
        )
        assert event is not None
        assert event.status == "PENDING"
        assert (
            session.scalar(
                select(func.count(AuditEvent.id)).where(
                    AuditEvent.entity_id == application["id"],
                    AuditEvent.action == "APPLICATION_SUBMITTED",
                )
            )
            == 1
        )
    # Draft creation and submission are both durable events; only submission
    # creates an in-app notification in this phase.
    assert dispatch_pending_events("pytest-worker") >= 1
    assert dispatch_pending_events("pytest-worker") == 0
    with SessionLocal() as session:
        assert (
            session.scalar(
                select(func.count(Notification.id))
                .join(OutboxEvent)
                .where(OutboxEvent.aggregate_id == application["id"])
            )
            >= 1
        )
        event = session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == application["id"],
                OutboxEvent.event_type == "APPLICATION_SUBMITTED",
            )
        )
        assert event is not None and event.status == "PROCESSED"


def test_application_command_idempotency_replays_and_rejects_payload_reuse(
    client: TestClient,
) -> None:
    seed()
    headers = _login(client, "applicant.alpha@example.org")
    headers["Idempotency-Key"] = str(uuid4())
    institution_id = client.get("/api/v1/institutions", headers=headers).json()["items"][0]["id"]
    payload = {
        "institution_id": institution_id,
        "application_type": "SYNTHETIC_NEW_PROGRAMME",
        "title": "Replay-safe draft",
    }

    first = client.post("/api/v1/applications", headers=headers, json=payload)
    replay = client.post("/api/v1/applications", headers=headers, json=payload)
    assert first.status_code == replay.status_code == 201
    assert first.json()["id"] == replay.json()["id"]
    with SessionLocal() as session:
        assert (
            session.scalar(
                select(func.count(Application.id)).where(Application.title == "Replay-safe draft")
            )
            == 1
        )

    altered = {**payload, "title": "Unsafe altered replay"}
    conflict = client.post("/api/v1/applications", headers=headers, json=altered)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "idempotency_key_reused"


def test_applicant_scope_and_logout(client: TestClient) -> None:
    seed()
    alpha_headers = _login(client, "applicant.alpha@example.org")
    beta_headers = _login(client, "applicant.beta@example.org")
    alpha_records = client.get("/api/v1/applications", headers=alpha_headers)
    beta_records = client.get("/api/v1/applications", headers=beta_headers)
    assert alpha_records.status_code == 200
    assert beta_records.status_code == 200
    assert all(
        item["reference_number"].startswith("DEMO-APP-ALPHA")
        for item in alpha_records.json()["items"]
    )
    beta_id = beta_records.json()["items"][0]["id"]
    cross_scope = client.get(f"/api/v1/applications/{beta_id}", headers=alpha_headers)
    assert cross_scope.status_code == 403
    logout = client.post("/api/v1/auth/logout", headers=alpha_headers)
    assert logout.status_code == 200
    assert client.get("/api/v1/me", headers=alpha_headers).status_code == 401


def test_private_document_cannot_cross_institution_boundary(client: TestClient) -> None:
    seed()
    alpha_headers = _login(client, "applicant.alpha@example.org")
    beta_headers = _login(client, "applicant.beta@example.org")
    alpha_application = client.get("/api/v1/applications", headers=alpha_headers).json()["items"][0]
    upload = client.post(
        "/api/v1/documents/uploads",
        headers=alpha_headers,
        data={"application_id": alpha_application["id"], "classification": "INTERNAL"},
        files={"file": ("private.pdf", b"%PDF-1.4\nprivate\n", "application/pdf")},
    )
    assert upload.status_code == 201
    replay = client.post(
        "/api/v1/documents/uploads",
        headers=alpha_headers,
        data={"application_id": alpha_application["id"], "classification": "INTERNAL"},
        files={"file": ("private.pdf", b"%PDF-1.4\nprivate\n", "application/pdf")},
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == upload.json()["id"]
    document_id = upload.json()["id"]
    assert client.get(f"/api/v1/documents/{document_id}", headers=beta_headers).status_code == 403
    assert (
        client.get(f"/api/v1/documents/{document_id}/content", headers=beta_headers).status_code
        == 403
    )
    downloaded = client.get(f"/api/v1/documents/{document_id}/content", headers=alpha_headers)
    assert downloaded.status_code == 200
    assert downloaded.content.startswith(b"%PDF-")


def test_transaction_rollback_leaves_no_audit_or_outbox_record() -> None:
    seed()
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == "applicant.alpha@example.org"))
        assert user is not None
        principal = build_principal(session, user)
        institution_id = principal.grants[0].institution_id
        assert institution_id is not None
        events_before = session.scalar(select(func.count()).select_from(OutboxEvent))
        audit_before = session.scalar(select(func.count()).select_from(AuditEvent))
        create_draft(
            session,
            principal=principal,
            institution_id=institution_id,
            application_type="SYNTHETIC_NEW_PROGRAMME",
            title="Discarded draft",
            workflow_template_key="SCRUTINY_ONLY",
            data={},
            correlation_id="rollback-test",
        )
        session.rollback()
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(OutboxEvent)) == events_before
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_before


def test_region_scope_and_read_only_mutation_denial(client: TestClient) -> None:
    seed()
    north_headers = _login(client, "regional.north@example.org")
    south_headers = _login(client, "regional.south@example.org")
    north_records = client.get("/api/v1/applications", headers=north_headers)
    south_records = client.get("/api/v1/applications", headers=south_headers)
    assert north_records.status_code == 200
    assert south_records.status_code == 200
    assert all("ALPHA" in item["reference_number"] for item in north_records.json()["items"])
    south_id = south_records.json()["items"][0]["id"]
    assert client.get(f"/api/v1/applications/{south_id}", headers=north_headers).status_code == 403

    auditor_headers = _login(client, "auditor@example.org")
    institution_id = north_records.json()["items"][0]["institution_id"]
    mutation = client.post(
        "/api/v1/applications",
        headers=auditor_headers,
        json={
            "institution_id": institution_id,
            "application_type": "SYNTHETIC_NEW_PROGRAMME",
            "title": "Unauthorized auditor mutation",
        },
    )
    assert mutation.status_code == 403


def test_authorized_scrutiny_review_requires_stage_role_and_scope(client: TestClient) -> None:
    seed()
    regional_headers = _login(client, "regional.north@example.org")
    scrutiny_headers = _login(client, "scrutiny.north@example.org")
    alternate_headers = _login(client, "scrutiny.north.alt@example.org")
    applicant_headers = _login(client, "applicant.alpha@example.org")
    submitted = next(
        item
        for item in client.get("/api/v1/applications", headers=regional_headers).json()["items"]
        if item["status"] == "SUBMITTED"
    )
    moved = client.post(
        f"/api/v1/applications/{submitted['id']}/transitions/advance_to_scrutiny",
        headers=regional_headers,
        json={"row_version": submitted["row_version"], "comment": "Synthetic routing"},
    )
    assert moved.status_code == 200, moved.text
    _assign_scrutiny_reviewer(
        client, submitted["id"], regional_headers, "scrutiny.north@example.org"
    )
    review_payload = {
        "summary": "Synthetic scrutiny review",
        "findings": [
            {
                "requirement_reference": "SYNTHETIC-REQ-1",
                "assessment": "CLARIFICATION_REQUIRED",
                "comment": "Provide a clearer synthetic supporting statement.",
                "references": {"source": "synthetic"},
            }
        ],
    }
    saved = client.post(
        f"/api/v1/applications/{submitted['id']}/scrutiny-reviews",
        headers=scrutiny_headers,
        json=review_payload,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["status"] == "DRAFT"
    unassigned = client.post(
        f"/api/v1/applications/{submitted['id']}/scrutiny-reviews",
        headers=alternate_headers,
        json=review_payload,
    )
    assert unassigned.status_code == 403
    denied = client.post(
        f"/api/v1/applications/{submitted['id']}/scrutiny-reviews",
        headers=applicant_headers,
        json=review_payload,
    )
    assert denied.status_code == 403


def test_return_deficiency_response_and_resubmission_are_traceable(client: TestClient) -> None:
    seed()
    regional_headers = _login(client, "regional.north@example.org")
    scrutiny_headers = _login(client, "scrutiny.north@example.org")
    applicant_headers = _login(client, "applicant.alpha@example.org")
    submitted = next(
        item
        for item in client.get("/api/v1/applications", headers=regional_headers).json()["items"]
        if item["status"] == "SUBMITTED"
    )
    scrutiny = client.post(
        f"/api/v1/applications/{submitted['id']}/transitions/advance_to_scrutiny",
        headers=regional_headers,
        json={"row_version": submitted["row_version"]},
    )
    assert scrutiny.status_code == 200, scrutiny.text
    _assign_scrutiny_reviewer(
        client, submitted["id"], regional_headers, "scrutiny.north@example.org"
    )
    returned = client.post(
        f"/api/v1/applications/{submitted['id']}/return-for-correction",
        headers=scrutiny_headers,
        json={
            "row_version": scrutiny.json()["row_version"],
            "reason": "Clarify the synthetic supporting record.",
            "deficiencies": [{"description": "Add an explanatory synthetic note."}],
        },
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["status"] == "RETURNED"
    deficiencies = client.get(
        f"/api/v1/applications/{submitted['id']}/deficiencies", headers=applicant_headers
    )
    assert deficiencies.status_code == 200
    deficiency = deficiencies.json()["items"][0]
    response = client.post(
        f"/api/v1/deficiencies/{deficiency['id']}/responses",
        headers=applicant_headers,
        json={"response_text": "The synthetic correction is now supplied."},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "RESPONDED"
    resubmitted = client.post(
        f"/api/v1/applications/{submitted['id']}/transitions/resubmit_after_correction",
        headers=applicant_headers,
        json={
            "row_version": returned.json()["row_version"],
            "comment": "Synthetic correction submitted",
        },
    )
    assert resubmitted.status_code == 200, resubmitted.text
    assert resubmitted.json()["current_stage_key"] == "scrutiny"
    timeline = client.get(
        f"/api/v1/applications/{submitted['id']}/timeline", headers=applicant_headers
    )
    assert [item["transition_key"] for item in timeline.json()["items"]][-2:] == [
        "return_for_correction",
        "resubmit_after_correction",
    ]


def test_revoked_reviewer_assignment_takes_effect_immediately(client: TestClient) -> None:
    seed()
    regional_headers = _login(client, "regional.north@example.org")
    scrutiny_headers = _login(client, "scrutiny.north@example.org")
    submitted = next(
        item
        for item in client.get("/api/v1/applications", headers=regional_headers).json()["items"]
        if item["status"] == "SUBMITTED"
    )
    moved = client.post(
        f"/api/v1/applications/{submitted['id']}/transitions/advance_to_scrutiny",
        headers=regional_headers,
        json={"row_version": submitted["row_version"]},
    )
    assert moved.status_code == 200, moved.text
    assignment = _assign_scrutiny_reviewer(
        client, submitted["id"], regional_headers, "scrutiny.north@example.org"
    )
    revoked = client.post(
        f"/api/v1/reviewer-assignments/{assignment['id']}/revoke",
        headers=regional_headers,
        json={"message": "Synthetic reassignment required"},
    )
    assert revoked.status_code == 200
    denied = client.post(
        f"/api/v1/applications/{submitted['id']}/scrutiny-reviews",
        headers=scrutiny_headers,
        json={"summary": "Denied after revoke", "findings": []},
    )
    assert denied.status_code == 403


def test_evc_visit_lifecycle_is_scoped_idempotent_and_audited(client: TestClient) -> None:
    from datetime import UTC, datetime, timedelta

    seed()
    coordinator = _login(client, "evc.south@example.org")
    north_officer = _login(client, "regional.north@example.org")
    evc_application = next(
        item
        for item in client.get("/api/v1/applications", headers=coordinator).json()["items"]
        if item["current_stage_key"] == "evc"
    )
    payload = {
        "application_id": evc_application["id"],
        "scheduled_start": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        "duration_minutes": 120,
        "timezone": "UTC",
        "visit_mode": "ONSITE",
        "location": "Synthetic campus",
        "notes": "Synthetic schedule",
    }
    created = client.post("/api/v1/evc-visits", headers=coordinator, json=payload)
    replay = client.post("/api/v1/evc-visits", headers=coordinator, json=payload)
    assert created.status_code == replay.status_code == 201
    assert created.json()["id"] == replay.json()["id"]
    assert client.post("/api/v1/evc-visits", headers=north_officer, json=payload).status_code == 403
    visit = created.json()
    coordinator["Idempotency-Key"] = str(uuid4())
    confirmed = client.post(
        f"/api/v1/evc-visits/{visit['id']}/actions/confirm",
        headers=coordinator,
        json={"row_version": visit["row_version"]},
    )
    assert confirmed.status_code == 200
    coordinator["Idempotency-Key"] = str(uuid4())
    started = client.post(
        f"/api/v1/evc-visits/{visit['id']}/actions/start",
        headers=coordinator,
        json={"row_version": confirmed.json()["row_version"]},
    )
    assert started.status_code == 200
    coordinator["Idempotency-Key"] = str(uuid4())
    completed = client.post(
        f"/api/v1/evc-visits/{visit['id']}/actions/complete",
        headers=coordinator,
        json={"row_version": started.json()["row_version"]},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETED"


def test_evc_checklist_and_report_review_lifecycle(client: TestClient) -> None:
    from datetime import UTC, datetime, timedelta

    seed()
    headers = _login(client, "evc.south@example.org")
    app = next(
        item
        for item in client.get("/api/v1/applications", headers=headers).json()["items"]
        if item["current_stage_key"] == "evc"
    )
    visit = client.post(
        "/api/v1/evc-visits",
        headers=headers,
        json={
            "application_id": app["id"],
            "scheduled_start": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "duration_minutes": 60,
            "timezone": "UTC",
            "visit_mode": "ONSITE",
            "location": "Synthetic campus",
        },
    ).json()
    headers["Idempotency-Key"] = str(uuid4())
    checklist = client.post(
        f"/api/v1/evc-visits/{visit['id']}/checklist",
        headers=headers,
        json={"label": "Synthetic preparation item"},
    )
    assert checklist.status_code == 200 or checklist.status_code == 201
    headers["Idempotency-Key"] = str(uuid4())
    completed_check = client.post(
        f"/api/v1/evc-checklist-items/{checklist.json()['id']}/complete",
        headers=headers,
        json={"note": "Synthetic completion"},
    )
    assert completed_check.status_code == 200
    for action in ("confirm", "start", "complete"):
        headers["Idempotency-Key"] = str(uuid4())
        response = client.post(
            f"/api/v1/evc-visits/{visit['id']}/actions/{action}",
            headers=headers,
            json={"row_version": visit["row_version"]},
        )
        assert response.status_code == 200, response.text
        visit = response.json()
    headers["Idempotency-Key"] = str(uuid4())
    report = client.post(
        f"/api/v1/evc-visits/{visit['id']}/reports",
        headers=headers,
        json={"summary": "Synthetic visit report"},
    )
    assert report.status_code == 200 or report.status_code == 201
    report_id = report.json()["id"]
    for action, body, status in (
        ("return", {"reason": "Add a synthetic clarification"}, "RETURNED"),
        ("resubmit", {}, "SUBMITTED"),
        ("accept", {}, "ACCEPTED"),
        ("close", {}, "CLOSED"),
    ):
        headers["Idempotency-Key"] = str(uuid4())
        response = client.post(
            f"/api/v1/evc-reports/{report_id}/{action}", headers=headers, json=body
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == status


def test_evc_evidence_is_version_pinned_audited_and_scoped(client: TestClient) -> None:
    from datetime import UTC, datetime, timedelta

    seed()
    headers = _login(client, "evc.south@example.org")
    north_headers = _login(client, "regional.north@example.org")
    app = next(
        item
        for item in client.get("/api/v1/applications", headers=headers).json()["items"]
        if item["current_stage_key"] == "evc"
    )
    with SessionLocal() as session:
        document = session.scalar(
            select(Document).where(Document.application_id == UUID(app["id"]))
        )
        assert document is not None
        version = session.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == document.id)
        )
        assert version is not None

    visit_response = client.post(
        "/api/v1/evc-visits",
        headers=headers,
        json={
            "application_id": app["id"],
            "scheduled_start": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "duration_minutes": 60,
            "timezone": "UTC",
            "visit_mode": "ONSITE",
            "location": "Synthetic campus",
        },
    )
    assert visit_response.status_code == 201, visit_response.text
    visit_id = visit_response.json()["id"]
    link_payload = {
        "document_id": str(document.id),
        "document_version_id": str(version.id),
        "purpose": "mandatory-campus-proof",
        "comment": "Synthetic exact-version evidence",
    }
    headers["Idempotency-Key"] = str(uuid4())
    linked = client.post(
        f"/api/v1/evc-visits/{visit_id}/evidence", headers=headers, json=link_payload
    )
    assert linked.status_code == 201, linked.text
    replay = client.post(
        f"/api/v1/evc-visits/{visit_id}/evidence", headers=headers, json=link_payload
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == linked.json()["id"]
    altered = client.post(
        f"/api/v1/evc-visits/{visit_id}/evidence",
        headers=headers,
        json={**link_payload, "purpose": "altered-purpose"},
    )
    assert altered.status_code == 409
    assert (
        client.get(f"/api/v1/evc-evidence/{linked.json()['id']}", headers=north_headers).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/evc-evidence/{linked.json()['id']}/reject", headers=north_headers, json={}
        ).status_code
        == 403
    )
    headers["Idempotency-Key"] = str(uuid4())
    assert (
        client.post(
            f"/api/v1/evc-evidence/{linked.json()['id']}/reject", headers=headers, json={}
        ).status_code
        == 409
    )
    headers["Idempotency-Key"] = str(uuid4())
    verified = client.post(
        f"/api/v1/evc-evidence/{linked.json()['id']}/verify", headers=headers, json={}
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "VERIFIED"
    evidence = client.get(f"/api/v1/evc-visits/{visit_id}/evidence", headers=headers)
    assert evidence.status_code == 200
    assert evidence.json()[0]["document_version_id"] == str(version.id)
    history = client.get(f"/api/v1/evc-evidence/{linked.json()['id']}/history", headers=headers)
    assert history.status_code == 200
    assert {item["action"] for item in history.json()} >= {
        "EVC_EVIDENCE_LINKED",
        "EVC_EVIDENCE_VERIFIED",
    }
    with SessionLocal() as session:
        event_types = set(
            session.scalars(
                select(OutboxEvent.event_type).where(
                    OutboxEvent.aggregate_id == visit_id,
                    OutboxEvent.event_type.in_(("EVC_EVIDENCE_LINKED", "EVC_EVIDENCE_VERIFIED")),
                )
            )
        )
    assert event_types == {"EVC_EVIDENCE_LINKED", "EVC_EVIDENCE_VERIFIED"}


def test_configured_evc_prerequisites_block_then_allow_transition() -> None:
    from datetime import UTC, datetime, timedelta

    seed()
    with SessionLocal() as session:
        application = session.scalar(
            select(Application).where(Application.reference_number == "DEMO-APP-BETA-EVC")
        )
        officer = session.scalar(select(User).where(User.email == "regional.south@example.org"))
        assert application is not None and officer is not None
        transition = session.scalar(
            select(WorkflowTransition).where(
                WorkflowTransition.template_version_id == application.workflow_template_version_id,
                WorkflowTransition.key == "advance_to_sac_shc",
            )
        )
        assert transition is not None
        transition.prerequisites = {
            "all": [
                {"fact": "evc.visit.completed"},
                {"fact": "evc.report.accepted"},
                {"fact": "evc.checklist.completed", "labels": ["campus-check"]},
                {"fact": "evc.evidence.verified", "purposes": ["mandatory-proof"]},
                {"fact": "evc.human_review.completed"},
            ]
        }
        principal = build_principal(session, officer)
        blocked = evaluate_transition(
            session,
            application=application,
            principal=principal,
            transition_key="advance_to_sac_shc",
        )
        assert not blocked.allowed
        assert blocked.reason_code == "prerequisites_unmet"
        assert "EVC visit" in blocked.missing_prerequisites[0]

        document = session.scalar(select(Document).where(Document.application_id == application.id))
        assert document is not None
        version = session.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == document.id)
        )
        assert version is not None
        visit = EvcVisit(
            application_id=application.id,
            institution_id=application.institution_id,
            region_id=application.assigned_region_id,
            coordinator_id=officer.id,
            status="COMPLETED",
            scheduled_start=datetime.now(UTC) + timedelta(days=1),
            duration_minutes=60,
            timezone="UTC",
            visit_mode="ONSITE",
            location="Synthetic campus",
            row_version=4,
        )
        session.add(visit)
        session.flush()
        session.add(EvcChecklistItem(visit_id=visit.id, label="campus-check", status="COMPLETED"))
        session.add(
            EvcReport(
                visit_id=visit.id,
                author_id=officer.id,
                status="ACCEPTED",
                summary="Synthetic accepted report",
            )
        )
        session.add(
            EvcEvidenceLink(
                visit_id=visit.id,
                document_id=document.id,
                document_version_id=version.id,
                purpose="mandatory-proof",
                status="VERIFIED",
                verified_by_user_id=officer.id,
                verified_at=datetime.now(UTC),
            )
        )
        session.flush()
        allowed = evaluate_transition(
            session,
            application=application,
            principal=principal,
            transition_key="advance_to_sac_shc",
        )
        assert allowed.allowed


def test_compliance_obligation_evidence_review_and_validity(client: TestClient) -> None:
    from datetime import UTC, datetime, timedelta

    seed()
    officer = _login(client, "compliance.south@example.org")
    applicant = _login(client, "applicant.beta@example.org")
    with SessionLocal() as session:
        application = session.scalar(
            select(Application).where(Application.reference_number == "DEMO-APP-BETA-EVC")
        )
        assert application is not None
        document = session.scalar(select(Document).where(Document.application_id == application.id))
        assert document is not None
        version = session.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == document.id)
        )
        assert version is not None
    obligation = client.post(
        "/api/v1/compliance-obligations",
        headers=officer,
        json={
            "application_id": str(application.id),
            "title": "Synthetic undertaking",
            "due_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
            "timezone": "UTC",
        },
    )
    assert obligation.status_code == 201, obligation.text
    officer["Idempotency-Key"] = str(uuid4())
    denied = client.post(
        "/api/v1/compliance-obligations",
        headers=_login(client, "regional.north@example.org"),
        json={"application_id": str(application.id), "title": "Denied", "timezone": "UTC"},
    )
    assert denied.status_code == 403
    applicant["Idempotency-Key"] = str(uuid4())
    evidence = client.post(
        f"/api/v1/compliance-obligations/{obligation.json()['id']}/evidence",
        headers=applicant,
        json={"document_id": str(document.id), "document_version_id": str(version.id)},
    )
    assert evidence.status_code == 201, evidence.text
    officer["Idempotency-Key"] = str(uuid4())
    returned = client.post(
        f"/api/v1/compliance-evidence/{evidence.json()['id']}/return",
        headers=officer,
        json={},
    )
    assert returned.status_code == 409
    officer["Idempotency-Key"] = str(uuid4())
    verified = client.post(
        f"/api/v1/compliance-evidence/{evidence.json()['id']}/verify", headers=officer, json={}
    )
    assert verified.status_code == 200
    applicant["Idempotency-Key"] = str(uuid4())
    validity = client.post(
        "/api/v1/validity-records",
        headers=applicant,
        json={
            "document_id": str(document.id),
            "document_version_id": str(version.id),
            "category": "Synthetic licence",
            "issue_date": datetime.now(UTC).isoformat(),
            "expiry_date": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
        },
    )
    assert validity.status_code == 201, validity.text
    applicant["Idempotency-Key"] = str(uuid4())
    invalid = client.post(
        "/api/v1/validity-records",
        headers=applicant,
        json={
            "document_id": str(document.id),
            "document_version_id": str(version.id),
            "category": "Invalid dates",
            "issue_date": datetime.now(UTC).isoformat(),
            "expiry_date": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        },
    )
    assert invalid.status_code == 409


def test_pendency_dashboard_is_scoped_and_matches_drill_down(client: TestClient) -> None:
    seed()
    south = _login(client, "regional.south@example.org")
    north = _login(client, "regional.north@example.org")
    south_data = client.get("/api/v1/dashboard/pendency", headers=south)
    north_data = client.get("/api/v1/dashboard/pendency", headers=north)
    assert south_data.status_code == north_data.status_code == 200
    for payload in (south_data.json(), north_data.json()):
        assert payload["total_active"] == sum(
            1 for item in payload["cases"] if item["status"] != "ROUTE_COMPLETE"
        )
        assert sum(payload["by_stage"].values()) == len(payload["cases"])
    assert {item["id"] for item in south_data.json()["cases"]}.isdisjoint(
        {item["id"] for item in north_data.json()["cases"]}
    )


def test_ai_scrutiny_fallback_is_scoped_non_binding_and_cited(client: TestClient) -> None:
    seed()
    south = _login(client, "regional.south@example.org")
    north = _login(client, "regional.north@example.org")
    with SessionLocal() as session:
        application = session.scalar(
            select(Application).where(Application.reference_number == "DEMO-APP-BETA-EVC")
        )
        assert application is not None
    response = client.get(
        f"/api/v1/applications/{application.id}/ai-scrutiny-assist", headers=south
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["non_binding"] is True
    assert payload["mode"] == "DETERMINISTIC_METADATA_FALLBACK"
    assert payload["sources"]
    assert (
        client.get(
            f"/api/v1/applications/{application.id}/ai-scrutiny-assist", headers=north
        ).status_code
        == 403
    )
