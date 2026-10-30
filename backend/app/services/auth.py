from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AuthenticationError, ConflictError, DomainError
from app.core.security import create_access_token, fingerprint_token, hash_password, verify_password
from app.models import AuthSession, LoginAttempt, User
from app.permissions.access import Principal, build_principal
from app.services.audit import record_audit_event


def _normalized_email(email: str) -> str:
    return email.strip().lower()


def _as_utc(value: datetime) -> datetime:
    """Defend against legacy/driver values that omit timezone information."""

    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _record_login_attempt(
    session: Session, email: str, success: bool, ip_address: str | None
) -> None:
    session.add(
        LoginAttempt(identity_key=_normalized_email(email), success=success, ip_address=ip_address)
    )


def _registration_identity(ip_address: str | None) -> str:
    """Rate-limit account requests independently of sign-in attempts."""

    return f"registration:{ip_address or 'unknown'}"


def _record_registration_attempt(
    session: Session, *, success: bool, ip_address: str | None
) -> None:
    # LoginAttempt is an existing durable, indexed auth-attempt ledger. A
    # namespaced identity keeps registration throttling separate from login.
    _record_login_attempt(session, _registration_identity(ip_address), success, ip_address)


def register_local_user(
    session: Session,
    *,
    display_name: str,
    email: str,
    password: str,
    ip_address: str | None,
    settings: Settings | None = None,
) -> User:
    """Create a pending account request without granting any role or scope."""

    settings = settings or get_settings()
    normalized_email = _normalized_email(email)
    normalized_name = display_name.strip()
    if len(normalized_name) < 2:
        raise DomainError(422, "invalid_display_name", "Enter a name with at least 2 characters.")
    if len(password) < settings.auth_registration_password_min_length:
        raise DomainError(
            422,
            "password_too_short",
            (
                "Password must be at least "
                f"{settings.auth_registration_password_min_length} characters."
            ),
        )

    cutoff = datetime.now(UTC) - timedelta(minutes=settings.auth_registration_window_minutes)
    attempts = session.scalar(
        select(func.count(LoginAttempt.id)).where(
            LoginAttempt.identity_key == _registration_identity(ip_address),
            LoginAttempt.success.is_(False),
            LoginAttempt.created_at >= cutoff,
        )
    )
    if int(attempts or 0) >= settings.auth_registration_max_attempts:
        raise DomainError(
            429,
            "registration_rate_limited",
            "Too many account requests. Try again later.",
        )

    # The unique database constraint remains the final guard. The preflight
    # lets us return the same intentionally non-enumerating response for the
    # usual duplicate case without ever exposing a user record.
    if session.scalar(select(User.id).where(User.email == normalized_email)) is not None:
        _record_registration_attempt(session, success=False, ip_address=ip_address)
        raise ConflictError(
            (
                "This email cannot be registered. Sign in if you already have an account "
                "or contact an administrator."
            ),
            code="registration_unavailable",
        )

    user = User(
        email=normalized_email,
        display_name=normalized_name,
        password_hash=hash_password(password),
        is_active=False,
        registration_status="PENDING",
    )
    try:
        # A savepoint keeps the durable failed-attempt record available if a
        # concurrent request wins the database unique constraint.
        with session.begin_nested():
            session.add(user)
            session.flush()
    except IntegrityError as exc:
        _record_registration_attempt(session, success=False, ip_address=ip_address)
        raise ConflictError(
            (
                "This email cannot be registered. Sign in if you already have an account "
                "or contact an administrator."
            ),
            code="registration_unavailable",
        ) from exc

    _record_registration_attempt(session, success=True, ip_address=ip_address)
    record_audit_event(
        session,
        actor=None,
        action="AUTH_REGISTRATION_REQUESTED",
        entity_type="USER",
        entity_id=str(user.id),
        after_summary={"activation_status": "PENDING_ADMINISTRATOR_APPROVAL"},
    )
    return user


def authenticate_local_user(
    session: Session,
    *,
    email: str,
    password: str,
    ip_address: str | None,
    settings: Settings | None = None,
) -> tuple[str, User, Principal]:
    """Authenticate a local-development account through a replaceable IdP boundary."""

    settings = settings or get_settings()
    normalized_email = _normalized_email(email)
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.auth_login_window_minutes)
    failures = session.scalar(
        select(func.count(LoginAttempt.id)).where(
            LoginAttempt.identity_key == normalized_email,
            LoginAttempt.success.is_(False),
            LoginAttempt.created_at >= cutoff,
        )
    )
    if int(failures or 0) >= settings.auth_login_max_attempts:
        raise DomainError(429, "login_rate_limited", "Too many sign-in attempts. Try again later.")

    user = session.scalar(select(User).where(User.email == normalized_email))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        _record_login_attempt(session, normalized_email, False, ip_address)
        raise AuthenticationError("Invalid email or password")

    auth_session = AuthSession(
        user_id=user.id,
        token_hash="pending",
        expires_at=datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes),
    )
    session.add(auth_session)
    session.flush()
    token, expires_at = create_access_token(str(user.id), str(auth_session.id), settings)
    auth_session.token_hash = fingerprint_token(token)
    auth_session.expires_at = expires_at
    user.last_login_at = datetime.now(UTC)
    _record_login_attempt(session, normalized_email, True, ip_address)
    principal = build_principal(session, user)
    record_audit_event(
        session,
        actor=principal,
        action="AUTH_LOGIN",
        entity_type="USER",
        entity_id=str(user.id),
        correlation_id=None,
        after_summary={"email": user.email, "authentication_method": "local_development"},
    )
    return token, user, principal


def authenticated_principal(
    session: Session, token: str, settings: Settings | None = None
) -> Principal:
    from app.core.security import decode_access_token

    claims = decode_access_token(token, settings)
    try:
        session_id = UUID(claims["session_id"])
        user_id = UUID(claims["user_id"])
    except (ValueError, KeyError) as exc:
        raise AuthenticationError("Invalid credentials") from exc
    auth_session = session.get(AuthSession, session_id)
    now = datetime.now(UTC)
    if (
        auth_session is None
        or auth_session.user_id != user_id
        or auth_session.revoked_at is not None
        or _as_utc(auth_session.expires_at) <= now
        or auth_session.token_hash != fingerprint_token(token)
    ):
        raise AuthenticationError("Invalid or expired credentials")
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Invalid or expired credentials")
    return build_principal(session, user)


def revoke_current_session(session: Session, token: str, principal: Principal) -> None:
    from app.core.security import decode_access_token

    claims = decode_access_token(token)
    auth_session = session.get(AuthSession, UUID(claims["session_id"]), with_for_update=True)
    if auth_session is None or auth_session.user_id != principal.user.id:
        raise AuthenticationError("Invalid or expired credentials")
    auth_session.revoked_at = datetime.now(UTC)
    record_audit_event(
        session,
        actor=principal,
        action="AUTH_LOGOUT",
        entity_type="AUTH_SESSION",
        entity_id=str(auth_session.id),
    )
