from __future__ import annotations

import pytest
from app.core.config import Settings
from app.core.security import verify_password
from app.db.seed import DEMO_PASSWORD, seed
from app.db.session import SessionLocal
from app.main import app
from app.models import AuditEvent, Institution, User
from fastapi.testclient import TestClient


def test_authentication_failures_are_generic_and_disabled_accounts_are_denied(
    client: TestClient,
) -> None:
    seed()
    wrong_password = client.post(
        "/api/v1/auth/login",
        json={"email": "applicant.alpha@example.org", "password": "not-the-password"},
    )
    unknown = client.post(
        "/api/v1/auth/login",
        json={"email": "unknown@example.org", "password": DEMO_PASSWORD},
    )
    assert wrong_password.status_code == 401
    assert unknown.status_code == 401
    assert (
        wrong_password.json()["detail"] == unknown.json()["detail"] == "Invalid email or password"
    )
    assert client.get("/api/v1/applications").status_code == 401


def test_disabled_account_cannot_login(client: TestClient) -> None:
    seed()
    with SessionLocal() as session:
        user = session.query(User).filter(User.email == "applicant.alpha@example.org").one()
        user.is_active = False
        session.commit()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "applicant.alpha@example.org", "password": DEMO_PASSWORD},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_registration_creates_pending_unprivileged_account_and_never_returns_a_secret(
    client: TestClient,
) -> None:
    seed()
    email = "new.registration@example.org"
    password = "synthetic-registration-password"
    response = client.post(
        "/api/v1/auth/register",
        json={"display_name": "New Registration", "email": email, "password": password},
    )

    assert response.status_code == 202, response.text
    assert response.json()["status"] == "PENDING_ADMINISTRATOR_APPROVAL"
    assert "access_token" not in response.json()
    with SessionLocal() as session:
        user = session.query(User).filter(User.email == email).one()
        assert user.display_name == "New Registration"
        assert user.is_active is False
        assert user.role_assignments == []
        assert user.password_hash != password
        assert verify_password(password, user.password_hash)
    # The account is persisted but cannot authenticate before explicit approval.
    pending_login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert pending_login.status_code == 401
    with TestClient(app) as restarted_client:
        assert (
            restarted_client.post("/api/v1/auth/login", json={"email": email, "password": password})
        ).status_code == 401


def test_registration_duplicate_and_privileged_role_attempt_are_rejected(
    client: TestClient,
) -> None:
    seed()
    registration = {
        "display_name": "Duplicate Registration",
        "email": "duplicate.registration@example.org",
        "password": "synthetic-registration-password",
    }
    assert client.post("/api/v1/auth/register", json=registration).status_code == 202
    duplicate = client.post("/api/v1/auth/register", json=registration)
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "registration_unavailable"
    assert "access_token" not in duplicate.json()

    privileged = client.post(
        "/api/v1/auth/register",
        json={
            "display_name": "No Privileged Role",
            "email": "privileged.request@example.org",
            "password": "synthetic-registration-password",
            "role": "SYSTEM_ADMINISTRATOR",
        },
    )
    assert privileged.status_code == 422
    with SessionLocal() as session:
        user = (
            session.query(User)
            .filter(User.email == "privileged.request@example.org")
            .one_or_none()
        )
        assert user is None


def test_login_creates_session_and_logout_revokes_it(client: TestClient) -> None:
    seed()
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "applicant.alpha@example.org", "password": DEMO_PASSWORD},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "logout-auth-test"}
    assert client.get("/api/v1/applications", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/v1/applications", headers=headers).status_code == 401


def test_authentication_payload_validation_and_password_policy(client: TestClient) -> None:
    missing_login_field = client.post("/api/v1/auth/login", json={"password": "synthetic"})
    malformed_registration = client.post(
        "/api/v1/auth/register",
        json={
            "display_name": "Malformed Email",
            "email": "not-an-email",
            "password": "synthetic-password",
        },
    )
    short_password = client.post(
        "/api/v1/auth/register",
        json={
            "display_name": "Short Password",
            "email": "short.password@example.org",
            "password": "short",
        },
    )

    assert missing_login_field.status_code == malformed_registration.status_code == 422
    assert (
        missing_login_field.json()["code"]
        == malformed_registration.json()["code"]
        == "validation_error"
    )
    assert short_password.status_code == 422
    assert short_password.json()["code"] == "password_too_short"


def _admin_headers(client: TestClient) -> dict[str, str]:
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.org", "password": DEMO_PASSWORD},
    )
    assert login.status_code == 200, login.text
    return {
        "Authorization": f"Bearer {login.json()['access_token']}",
        "Idempotency-Key": "user-admin-test-key",
    }


def _pending_user(client: TestClient, email: str):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "display_name": "Pending Administrator Test",
            "email": email,
            "password": "synthetic-registration-password",
        },
    )
    assert response.status_code == 202, response.text
    with SessionLocal() as session:
        return session.query(User).filter(User.email == email).one().id


def _institution_id() -> str:
    with SessionLocal() as session:
        return str(session.query(Institution).filter(Institution.is_active.is_(True)).first().id)


def test_global_administrator_can_approve_reject_and_audit_registration(client: TestClient) -> None:
    seed()
    pending_id = _pending_user(client, "pending.approval@example.org")
    headers = _admin_headers(client)
    pending = client.get("/api/v1/users?status=PENDING", headers=headers)
    assert pending.status_code == 200, pending.text
    assert any(item["id"] == str(pending_id) for item in pending.json())
    institution_id = _institution_id()
    approved = client.post(
        f"/api/v1/users/{pending_id}/approve",
        headers=headers,
        json={
            "role_key": "INSTITUTION_APPLICANT",
            "scope_type": "INSTITUTION",
            "institution_id": institution_id,
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["registration_status"] == "APPROVED"
    assert approved.json()["is_active"] is True
    assert approved.json()["roles"] == ["INSTITUTION_APPLICANT"]
    replayed = client.post(
        f"/api/v1/users/{pending_id}/approve",
        headers=headers,
        json={
            "role_key": "INSTITUTION_APPLICANT",
            "scope_type": "INSTITUTION",
            "institution_id": institution_id,
        },
    )
    assert replayed.status_code == 200
    assert replayed.json() == approved.json()
    with SessionLocal() as session:
        user = session.query(User).filter(User.id == pending_id).one()
        event = (
            session.query(AuditEvent)
            .filter(AuditEvent.action == "USER_REGISTRATION_APPROVED")
            .one()
        )
        assert user.registration_status == "APPROVED"
        assert event is not None

    rejected_id = _pending_user(client, "pending.rejection@example.org")
    rejected = client.post(
        f"/api/v1/users/{rejected_id}/reject",
        headers={**headers, "Idempotency-Key": "user-admin-reject-key"},
        json={"reason": "Synthetic verification could not be completed"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["registration_status"] == "REJECTED"
    assert rejected.json()["is_active"] is False


def test_user_administration_denies_non_admin_and_validates_role_scope(client: TestClient) -> None:
    seed()
    pending_id = _pending_user(client, "pending.denial@example.org")
    applicant_login = client.post(
        "/api/v1/auth/login",
        json={"email": "applicant.alpha@example.org", "password": DEMO_PASSWORD},
    )
    applicant_headers = {"Authorization": f"Bearer {applicant_login.json()['access_token']}"}
    assert client.get("/api/v1/users", headers=applicant_headers).status_code == 403

    headers = _admin_headers(client)
    invalid_scope = client.post(
        f"/api/v1/users/{pending_id}/approve",
        headers=headers,
        json={"role_key": "INSTITUTION_APPLICANT", "scope_type": "GLOBAL"},
    )
    assert invalid_scope.status_code == 409
    assert invalid_scope.json()["code"] == "invalid_role_scope"
    privileged_role = client.post(
        f"/api/v1/users/{pending_id}/approve",
        headers={**headers, "Idempotency-Key": "user-admin-privileged-key"},
        json={"role_key": "SYSTEM_ADMINISTRATOR", "scope_type": "GLOBAL"},
    )
    assert privileged_role.status_code == 403


def test_user_administrator_can_deactivate_and_revoke_approved_role(client: TestClient) -> None:
    seed()
    pending_id = _pending_user(client, "pending.lifecycle@example.org")
    headers = _admin_headers(client)
    institution_id = _institution_id()
    approved = client.post(
        f"/api/v1/users/{pending_id}/approve",
        headers=headers,
        json={
            "role_key": "INSTITUTION_APPLICANT",
            "scope_type": "INSTITUTION",
            "institution_id": institution_id,
        },
    )
    grant_id = approved.json()["grants"][0]["id"]
    deactivated = client.post(
        f"/api/v1/users/{pending_id}/activation",
        headers={**headers, "Idempotency-Key": "user-admin-deactivate-key"},
        json={"is_active": False},
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    assert client.post(
        "/api/v1/auth/login",
        json={
            "email": "pending.lifecycle@example.org",
            "password": "synthetic-registration-password",
        },
    ).status_code == 401
    revoked = client.delete(
        f"/api/v1/users/{pending_id}/roles/{grant_id}",
        headers={**headers, "Idempotency-Key": "user-admin-revoke-key"},
    )
    assert revoked.status_code == 200


def test_mutating_commands_require_idempotency_key(client: TestClient) -> None:
    seed()
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "applicant.alpha@example.org", "password": DEMO_PASSWORD},
    )
    token = login.json()["access_token"]
    institutions = client.get("/api/v1/institutions", headers={"Authorization": f"Bearer {token}"})
    response = client.post(
        "/api/v1/applications",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "institution_id": institutions.json()["items"][0]["id"],
            "application_type": "SYNTHETIC_NEW_PROGRAMME",
            "title": "Missing idempotency header",
        },
    )
    assert response.status_code == 422


def test_communication_put_cors_preflight_is_allowed(client: TestClient) -> None:
    response = client.options(
        "/api/v1/communications/00000000-0000-0000-0000-000000000000",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "authorization,content-type,idempotency-key",
        },
    )
    assert response.status_code == 200
    assert "PUT" in response.headers["access-control-allow-methods"]


def test_production_settings_reject_placeholder_or_short_jwt_secrets() -> None:
    for secret in ("replace-with-a-token", "too-short"):
        settings = Settings(
            environment="production",
            TOKEN_SIGNING_SECRET=secret,
            DATABASE_URL="postgresql+psycopg://example:example@localhost:5432/example",
            DEVELOPMENT_SEED_ENABLED=False,
        )
        with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
            settings.validate_production()
