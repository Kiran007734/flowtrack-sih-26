from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, EmailStr, Field

from app.schemas.common import ActorResponse, APIModel


class CurrentUserResponse(ActorResponse):
    permissions: list[str]


class LoginRequest(APIModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(APIModel):
    access_token: str
    token_type: str = "bearer"
    user: CurrentUserResponse


class RegistrationRequest(APIModel):
    """Public account-request payload.

    Role and scope fields are deliberately forbidden: public registration is
    an approval request, not an authorization grant.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="forbid")

    display_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class RegistrationResponse(APIModel):
    status: Literal["PENDING_ADMINISTRATOR_APPROVAL"]
    message: str


class UserAdminResponse(ActorResponse):
    registration_status: str
    created_at: str
    last_login_at: str | None
    grants: list[RoleGrantResponse]


class RoleGrantResponse(APIModel):
    id: UUID
    role_key: str
    role_name: str
    scope_type: str
    institution_id: UUID | None
    region_id: UUID | None
    is_active: bool


class RoleGrantRequest(APIModel):
    role_key: str = Field(min_length=1, max_length=80)
    scope_type: Literal["GLOBAL", "REGION", "INSTITUTION"]
    institution_id: UUID | None = None
    region_id: UUID | None = None


class AccountActivationRequest(APIModel):
    is_active: bool


class RegistrationDecisionRequest(RoleGrantRequest):
    pass


class RegistrationRejectionRequest(APIModel):
    reason: str = Field(min_length=3, max_length=500)
