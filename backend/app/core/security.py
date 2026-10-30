from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

import jwt
from pwdlib import PasswordHash

from app.core.config import Settings, get_settings
from app.core.errors import AuthenticationError

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def fingerprint_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def create_access_token(
    user_id: str, session_id: str, settings: Settings | None = None
) -> tuple[str, datetime]:
    settings = settings or get_settings()
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    claims = {
        "sub": user_id,
        "sid": session_id,
        "jti": str(uuid4()),
        "typ": "access",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": expires_at,
    }
    return (
        jwt.encode(
            claims, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm
        ),
        expires_at,
    )


def decode_access_token(token: str, settings: Settings | None = None) -> dict[str, str]:
    settings = settings or get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid or expired credentials") from exc
    if payload.get("typ") != "access" or not payload.get("sub") or not payload.get("sid"):
        raise AuthenticationError("Invalid credentials")
    return {"user_id": str(payload["sub"]), "session_id": str(payload["sid"])}
