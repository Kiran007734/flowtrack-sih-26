from __future__ import annotations

from typing import Any


class DomainError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        detail: str,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.extra = extra or {}


class AuthenticationError(DomainError):
    def __init__(self, detail: str = "Authentication is required") -> None:
        super().__init__(401, "authentication_required", detail)


class AuthorizationError(DomainError):
    def __init__(self, detail: str = "You are not permitted to perform this action") -> None:
        super().__init__(403, "forbidden", detail)


class NotFoundError(DomainError):
    def __init__(self, detail: str = "The requested resource was not found") -> None:
        super().__init__(404, "not_found", detail)


class ConflictError(DomainError):
    def __init__(
        self, detail: str, *, code: str = "conflict", extra: dict[str, Any] | None = None
    ) -> None:
        super().__init__(409, code, detail, extra=extra)


class PrerequisiteError(DomainError):
    def __init__(self, detail: str, missing: list[str]) -> None:
        super().__init__(
            422,
            "transition_blocked",
            detail,
            extra={"blocking_reasons": missing},
        )
