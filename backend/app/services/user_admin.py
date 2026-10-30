from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AuthorizationError, ConflictError, NotFoundError
from app.models import Institution, Region, Role, RoleAssignment, User
from app.permissions.access import Principal, require_permission
from app.services.audit import record_audit_event

_INSTITUTION_ROLES = {"INSTITUTION_APPLICANT", "INSTITUTION_ADMINISTRATOR"}
_REGION_ROLES = {
    "SCRUTINY_OFFICER",
    "REGIONAL_OFFICER",
    "REGIONAL_ADMINISTRATOR",
    "EVC_MEMBER",
    "EVC_COORDINATOR",
    "AUTHORIZED_REVIEWER",
    "COMPLIANCE_OFFICER",
}
_GLOBAL_ROLES = {"READ_ONLY_AUDITOR"}


def _admin(principal: Principal) -> None:
    require_permission(principal, "user.manage")
    if not any(grant.scope_type == "GLOBAL" for grant in principal.grants):
        raise AuthorizationError("User administration requires a global administrator grant")


def _user(session: Session, user_id: object) -> User:
    item = session.get(User, user_id)
    if item is None:
        raise NotFoundError("The requested user was not found")
    return item


def _validate_scope(
    session: Session,
    *,
    role_key: str,
    scope_type: str,
    institution_id: object | None,
    region_id: object | None,
) -> None:
    if role_key in _INSTITUTION_ROLES:
        valid = (
            scope_type == "INSTITUTION"
            and institution_id
            and not region_id
            and session.get(Institution, institution_id)
        )
        message = "This role requires one active institution scope"
    elif role_key in _REGION_ROLES:
        valid = (
            scope_type == "REGION"
            and region_id
            and not institution_id
            and session.get(Region, region_id)
        )
        message = "This role requires one active region scope"
    elif role_key in _GLOBAL_ROLES:
        valid = scope_type == "GLOBAL" and not institution_id and not region_id
        message = "This role requires global scope"
    else:
        valid = False
        message = "This role is not assignable"
    if not valid:
        raise ConflictError(message, code="invalid_role_scope")


def _grant(
    session: Session,
    *,
    user: User,
    role_key: str,
    scope_type: str,
    institution_id: object | None,
    region_id: object | None,
) -> RoleAssignment:
    role = session.scalar(select(Role).where(Role.key == role_key, Role.is_active.is_(True)))
    if role is None or role_key == "SYSTEM_ADMINISTRATOR":
        raise AuthorizationError("This role cannot be assigned through user administration")
    _validate_scope(
        session,
        role_key=role_key,
        scope_type=scope_type,
        institution_id=institution_id,
        region_id=region_id,
    )
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
    if existing:
        raise ConflictError("This active role grant already exists", code="duplicate_role_grant")
    item = RoleAssignment(
        user_id=user.id,
        role_id=role.id,
        scope_type=scope_type,
        institution_id=institution_id,
        region_id=region_id,
        is_active=True,
    )
    session.add(item)
    session.flush()
    return item


def list_users(
    session: Session, *, principal: Principal, status: str | None, query: str | None
) -> list[User]:
    _admin(principal)
    statement = select(User).order_by(User.created_at.desc()).limit(200)
    if status:
        statement = statement.where(User.registration_status == status.upper())
    if query:
        value = f"%{query.strip().lower()}%"
        statement = statement.where(
            func.lower(User.email).like(value) | func.lower(User.display_name).like(value)
        )
    return list(session.scalars(statement))


def get_user(session: Session, *, principal: Principal, user_id: object) -> User:
    _admin(principal)
    return _user(session, user_id)


def _audit(
    session: Session, principal: Principal, action: str, user: User, **details: object
) -> None:
    record_audit_event(
        session,
        actor=principal,
        action=action,
        entity_type="USER",
        entity_id=str(user.id),
        after_summary=details,
    )


def approve_registration(
    session: Session, *, principal: Principal, user_id: object, grant: dict
) -> User:
    _admin(principal)
    user = _user(session, user_id)
    if user.registration_status != "PENDING":
        raise ConflictError(
            "Only pending account requests can be approved", code="registration_not_pending"
        )
    _grant(session, user=user, **grant)
    user.registration_status, user.is_active = "APPROVED", True
    _audit(
        session,
        principal,
        "USER_REGISTRATION_APPROVED",
        user,
        registration_status="APPROVED",
        is_active=True,
        role_key=grant["role_key"],
        scope_type=grant["scope_type"],
    )
    return user


def reject_registration(
    session: Session, *, principal: Principal, user_id: object, reason: str
) -> User:
    _admin(principal)
    user = _user(session, user_id)
    if user.registration_status != "PENDING":
        raise ConflictError(
            "Only pending account requests can be rejected", code="registration_not_pending"
        )
    user.registration_status, user.is_active = "REJECTED", False
    record_audit_event(
        session,
        actor=principal,
        action="USER_REGISTRATION_REJECTED",
        entity_type="USER",
        entity_id=str(user.id),
        reason=reason,
        after_summary={"registration_status": "REJECTED", "is_active": False},
    )
    return user


def set_activation(
    session: Session, *, principal: Principal, user_id: object, is_active: bool
) -> User:
    _admin(principal)
    user = _user(session, user_id)
    if user.id == principal.user.id:
        raise AuthorizationError("Administrators cannot change their own activation status")
    if user.registration_status != "APPROVED":
        raise ConflictError("Only approved accounts can be activated", code="account_not_approved")
    user.is_active = is_active
    _audit(
        session,
        principal,
        "USER_ACCOUNT_ACTIVATED" if is_active else "USER_ACCOUNT_DEACTIVATED",
        user,
        is_active=is_active,
    )
    return user


def assign_role(
    session: Session, *, principal: Principal, user_id: object, grant: dict
) -> RoleAssignment:
    _admin(principal)
    user = _user(session, user_id)
    if user.registration_status != "APPROVED":
        raise ConflictError(
            "Roles may be assigned only to approved accounts", code="account_not_approved"
        )
    item = _grant(session, user=user, **grant)
    _audit(
        session,
        principal,
        "USER_ROLE_ASSIGNED",
        user,
        role_key=grant["role_key"],
        scope_type=grant["scope_type"],
    )
    return item


def revoke_role(
    session: Session, *, principal: Principal, user_id: object, grant_id: object
) -> None:
    _admin(principal)
    user = _user(session, user_id)
    item = session.get(RoleAssignment, grant_id)
    if item is None or item.user_id != user.id:
        raise NotFoundError("The requested role grant was not found")
    role = session.get(Role, item.role_id)
    if role is None or role.key == "SYSTEM_ADMINISTRATOR":
        raise AuthorizationError("This role cannot be revoked through user administration")
    item.is_active = False
    _audit(
        session, principal, "USER_ROLE_REVOKED", user, role_key=role.key, scope_type=item.scope_type
    )
