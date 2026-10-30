from __future__ import annotations

import json
import logging
from time import perf_counter
from uuid import uuid4

import redis
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1 import router as v1_router
from app.core.config import get_settings
from app.core.errors import DomainError
from app.db.session import engine
from app.storage import LocalPrivateStorage

settings = get_settings()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("correlation_id", "method", "path", "status_code", "duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, default=str)


def _configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(handler)
    root.setLevel(settings.log_level.upper())


_configure_logging()
logger = logging.getLogger("flowtrack.api")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Synthetic-data FlowTrack prototype API. Workflow configurations are not official "
        "AICTE rules."
    ),
    docs_url="/docs",
    openapi_url="/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Correlation-ID"],
    expose_headers=["X-Correlation-ID"],
)


@app.middleware("http")
async def correlation_and_request_log(request: Request, call_next: object) -> object:
    correlation_id = request.headers.get("X-Correlation-ID") or uuid4().hex
    request.state.correlation_id = correlation_id
    start = perf_counter()
    try:
        response = await call_next(request)  # type: ignore[misc]
    except Exception:
        logger.exception(
            "unhandled_request_error",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.url.path,
            },
        )
        raise
    response.headers["X-Correlation-ID"] = correlation_id
    logger.info(
        "request_complete",
        extra={
            "correlation_id": correlation_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((perf_counter() - start) * 1000, 2),
        },
    )
    return response


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    payload = {
        "type": f"https://flowtrack.local/problems/{exc.code}",
        "title": exc.code.replace("_", " ").title(),
        "status": exc.status_code,
        "code": exc.code,
        "detail": exc.detail,
        "trace_id": getattr(request.state, "correlation_id", None),
        **exc.extra,
    }
    return JSONResponse(
        status_code=exc.status_code, content=payload, media_type="application/problem+json"
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors: dict[str, list[str]] = {}
    for error in exc.errors():
        location = ".".join(
            str(part) for part in error["loc"] if part not in {"body", "query", "path"}
        )
        errors.setdefault(location or "request", []).append(error["msg"])
    return JSONResponse(
        status_code=422,
        media_type="application/problem+json",
        content={
            "type": "https://flowtrack.local/problems/validation_error",
            "title": "Validation error",
            "status": 422,
            "code": "validation_error",
            "detail": "One or more fields are invalid.",
            "errors": errors,
            "trace_id": getattr(request.state, "correlation_id", None),
        },
    )


@app.get("/health/live", tags=["Health"])
def live() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/health/ready", tags=["Health"])
def ready() -> JSONResponse:
    dependencies: dict[str, str] = {"configuration": "ok"}
    database_ok = False
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        database_ok = True
        dependencies["database"] = "ok"
    except Exception:
        dependencies["database"] = "unavailable"
    try:
        redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1).ping()
        dependencies["redis"] = "ok"
    except Exception:
        dependencies["redis"] = "unavailable"
    try:
        LocalPrivateStorage(settings.private_storage_root)
        dependencies["private_storage"] = "ok"
    except Exception:
        dependencies["private_storage"] = "unavailable"
    dependencies["ai"] = "not_configured"
    status = "ready" if database_ok and dependencies["private_storage"] == "ok" else "not_ready"
    code = 200 if status == "ready" else 503
    return JSONResponse(status_code=code, content={"status": status, "dependencies": dependencies})


app.include_router(v1_router, prefix=settings.api_v1_prefix)
