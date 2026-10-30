from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AuthenticationError
from app.db.session import get_db
from app.permissions.access import Principal
from app.services.auth import authenticated_principal

bearer_scheme = HTTPBearer(auto_error=False, scheme_name="bearerAuth")
DbSession = Annotated[Session, Depends(get_db)]


def get_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise AuthenticationError()
    return credentials.credentials


def get_current_principal(
    db: DbSession, token: Annotated[str, Depends(get_bearer_token)]
) -> Principal:
    return authenticated_principal(db, token)


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


def get_idempotency_key(
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=255)],
) -> str:
    """Require callers to make retryable command intent explicit."""

    return idempotency_key


IdempotencyKey = Annotated[str, Depends(get_idempotency_key)]
