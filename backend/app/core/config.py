from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed runtime settings; secrets are intentionally never rendered in logs."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "AICTE FlowTrack API"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    api_v1_prefix: str = Field(
        default="/api/v1", validation_alias=AliasChoices("API_V1_PREFIX", "API_PREFIX")
    )
    database_url: str = "postgresql+psycopg://flowtrack:flowtrack@localhost:5432/flowtrack"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    jwt_secret_key: SecretStr = Field(
        default=SecretStr("development-only-change-me-before-deploying"),
        validation_alias=AliasChoices("JWT_SECRET_KEY", "TOKEN_SIGNING_SECRET"),
    )
    jwt_algorithm: str = Field(
        default="HS256", validation_alias=AliasChoices("JWT_ALGORITHM", "TOKEN_ALGORITHM")
    )
    jwt_issuer: str = Field(
        default="flowtrack-local", validation_alias=AliasChoices("JWT_ISSUER", "TOKEN_ISSUER")
    )
    jwt_audience: str = Field(
        default="flowtrack-web", validation_alias=AliasChoices("JWT_AUDIENCE", "TOKEN_AUDIENCE")
    )
    access_token_expire_minutes: int = Field(default=30, ge=5, le=1440)
    cors_origins: list[str] = ["http://localhost:5173"]
    private_storage_backend: Literal["local"] = "local"
    private_storage_root: Path = Path("../storage/private")
    max_upload_size_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    max_ocr_page_count: int = Field(default=100, ge=1, le=1000)
    max_ocr_input_bytes: int = Field(default=25 * 1024 * 1024, ge=1)
    max_ocr_image_pixels: int = Field(default=20_000_000, ge=1)
    ocr_render_scale: float = Field(default=2.0, ge=0.5, le=4.0)
    ocr_timeout_seconds: int = Field(default=45, ge=1, le=300)
    ocr_executable_path: Path | None = None
    ocr_minimum_text_characters: int = Field(default=24, ge=1, le=10000)
    allowed_document_types: list[str] = ["application/pdf", "image/png", "image/jpeg"]
    development_seed_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("DEVELOPMENT_SEED_ENABLED", "ENABLE_DEVELOPMENT_SEED"),
    )
    log_level: str = "INFO"
    timezone: str = "UTC"
    notification_provider_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NOTIFICATION_PROVIDER_URL", "NOTIFICATION_PROVIDER"),
    )
    kms_key_reference: str | None = Field(
        default=None, validation_alias=AliasChoices("KMS_KEY_REFERENCE", "KMS_KEY_ID")
    )
    outbox_max_attempts: int = Field(default=5, ge=1, le=20)
    evc_reminder_lead_hours: int = Field(default=24, ge=1, le=720)
    evc_reminder_overdue_hours: int = Field(default=24, ge=1, le=720)
    auth_login_window_minutes: int = Field(default=15, ge=1, le=120)
    auth_login_max_attempts: int = Field(default=10, ge=1, le=100)
    auth_registration_window_minutes: int = Field(default=60, ge=1, le=1440)
    auth_registration_max_attempts: int = Field(default=5, ge=1, le=100)
    auth_registration_password_min_length: int = Field(default=12, ge=12, le=128)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("allowed_document_types", mode="before")
    @classmethod
    def parse_allowed_document_types(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip().lower() for item in value.split(",") if item.strip()]
        return value

    @property
    def effective_celery_broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def effective_celery_result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    def validate_production(self) -> None:
        if self.environment != "production":
            return
        secret = self.jwt_secret_key.get_secret_value()
        if (
            len(secret) < 32
            or secret == "development-only-change-me-before-deploying"
            or secret.lower().startswith("replace-")
        ):
            raise ValueError(
                "JWT_SECRET_KEY must be a non-placeholder value of at least 32 characters"
            )
        if self.development_seed_enabled:
            raise ValueError("DEVELOPMENT_SEED_ENABLED must be false in production")
        if not self.database_url.startswith("postgresql"):
            raise ValueError("Production requires a PostgreSQL database URL")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_production()
    return settings
