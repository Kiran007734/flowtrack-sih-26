from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from app.core.config import get_settings
from app.core.errors import AuthenticationError, DomainError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.db import seed as seed_module
from app.services.documents import safe_display_filename, validate_upload
from app.storage import LocalPrivateStorage, StorageError


def test_password_hash_and_token_round_trip() -> None:
    password_hash = hash_password("correct-horse-battery-staple")
    assert password_hash != "correct-horse-battery-staple"
    assert verify_password("correct-horse-battery-staple", password_hash)
    assert not verify_password("wrong", password_hash)
    token, _expires_at = create_access_token("user-id", "session-id")
    assert decode_access_token(token) == {"user_id": "user-id", "session_id": "session-id"}


def test_expired_or_invalid_tokens_are_rejected() -> None:
    settings = get_settings()
    expired = jwt.encode(
        {
            "sub": "user-id",
            "sid": "session-id",
            "typ": "access",
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": datetime.now(UTC) - timedelta(minutes=10),
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(AuthenticationError):
        decode_access_token(expired)
    with pytest.raises(AuthenticationError):
        decode_access_token("not-a-token")


def test_development_seed_requires_a_non_placeholder_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(seed_module, "DEMO_PASSWORD", "replace-with-a-password")
    with pytest.raises(RuntimeError, match="DEVELOPMENT_SEED_PASSWORD"):
        seed_module._development_seed_password()
    monkeypatch.setattr(seed_module, "DEMO_PASSWORD", "unique-local-test-password")
    assert seed_module._development_seed_password() == "unique-local-test-password"


def test_safe_filename_and_content_validation() -> None:
    settings = get_settings()
    name, mime, checksum = validate_upload(
        content=b"%PDF-1.4\nsynthetic\n",
        original_filename="../../evidence.pdf",
        supplied_mime_type="application/pdf",
        settings=settings,
    )
    assert name == "evidence.pdf"
    assert mime == "application/pdf"
    assert len(checksum) == 64
    assert safe_display_filename("..\\bad:name.pdf") == "bad_name.pdf"
    with pytest.raises(DomainError, match="extension"):
        validate_upload(
            content=b"%PDF-1.4\nsynthetic\n",
            original_filename="evidence.exe",
            supplied_mime_type="application/pdf",
            settings=settings,
        )


def test_local_private_storage_rejects_escape(tmp_path: Path) -> None:
    storage = LocalPrivateStorage(tmp_path)
    storage.store("documents/a/one", b"safe")
    assert storage.retrieve_path("documents/a/one").read_bytes() == b"safe"
    with pytest.raises(StorageError):
        storage.store("../escape", b"unsafe")
    assert not (tmp_path.parent / "escape").exists()
