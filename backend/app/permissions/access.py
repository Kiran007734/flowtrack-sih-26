from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AuthorizationError
from app.models import (
    Application,
    Institution,
    Permission,
    Role,
    RoleAssignment,
    RolePermission,
    User,
)


@dataclass(frozen=True)
class Principal:
    user: User
    role_keys: frozenset[str]
    permissions: frozenset[str]
    grants: tuple[RoleAssignment, ...]


def build_principal(session: Session, user: User) -> Principal:
    assignments = list(
        session.scalars(
            select(RoleAssignment).where(
                RoleAssignment.user_id == user.id, RoleAssignment.is_active.is_(True)
            )
        )
    )
    role_ids = [assignment.role_id for assignment in assignments]
    if not role_ids:
        return Principal(user=user, role_keys=frozenset(), permissions=frozenset(), grants=tuple())
    roles = list(
        session.scalars(select(Role).where(Role.id.in_(role_ids), Role.is_active.is_(True)))
    )
    role_key_by_id = {role.id: role.key for role in roles}
    active_role_ids = list(role_key_by_id)
    permission_codes = set(
        session.scalars(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id.in_(active_role_ids))
        )
    )
    active_assignments = tuple(item for item in assignments if item.role_id in role_key_by_id)
    return Principal(
        user=user,
        role_keys=frozenset(role_key_by_id.values()),
        permissions=frozenset(permission_codes),
        grants=active_assignments,
    )


def require_permission(principal: Principal, permission: str) -> None:
    if permission not in principal.permissions:
        raise AuthorizationError()


def _has_global_grant(principal: Principal) -> bool:
    return any(grant.scope_type == "GLOBAL" for grant in principal.grants)


def can_access_institution(principal: Principal, institution: Institution) -> bool:
    if _has_global_grant(principal):
        return True
    for grant in principal.grants:
        if grant.scope_type == "INSTITUTION" and grant.institution_id == institution.id:
            return True
        if grant.scope_type == "REGION" and grant.region_id == institution.region_id:
            return True
    return False


def require_institution_access(principal: Principal, institution: Institution) -> None:
    if not can_access_institution(principal, institution):
        raise AuthorizationError("You are not permitted to access this institution")


def can_access_application(principal: Principal, application: Application) -> bool:
    return can_access_institution(principal, application.institution)


def require_application_access(principal: Principal, application: Application) -> None:
    if not can_access_application(principal, application):
        raise AuthorizationError("You are not permitted to access this application")


def scoped_institution_ids(session: Session, principal: Principal) -> set[UUID] | None:
    """Return None for global scope; otherwise a non-authoritative filter set."""
    if _has_global_grant(principal):
        return None
    ids: set[UUID] = set()
    region_ids: set[UUID] = set()
    for grant in principal.grants:
        if grant.scope_type == "INSTITUTION" and grant.institution_id:
            ids.add(grant.institution_id)
        if grant.scope_type == "REGION" and grant.region_id:
            region_ids.add(grant.region_id)
    if region_ids:
        ids.update(
            session.scalars(select(Institution.id).where(Institution.region_id.in_(region_ids)))
        )
    return ids
