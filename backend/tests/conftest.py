from __future__ import annotations

import os
import shutil
from collections.abc import Generator
from pathlib import Path

# Set this before importing application modules; the production application is
# PostgreSQL-only, while these host-only tests exercise portable service logic.
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite://")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DEVELOPMENT_SEED_ENABLED", "true")
os.environ.setdefault("DEVELOPMENT_SEED_PASSWORD", "test-only-synthetic-password")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-not-for-production-000000000000")

import pytest
from app.core.config import get_settings
from app.db import session as db_module
from app.main import app
from app.models import Base
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool


@pytest.fixture(scope="session", autouse=True)
def sqlite_schema() -> Generator[None, None, None]:
    """Portable host-only fixture; PostgreSQL integration is separately marked."""

    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db_module.SessionLocal.configure(bind=engine)
    Base.metadata.create_all(engine)
    settings = get_settings()
    settings.environment = "test"
    settings.development_seed_enabled = True
    storage_root = Path("tests/.private-storage").resolve()
    settings.private_storage_root = storage_root
    yield
    Base.metadata.drop_all(engine)
    if storage_root.exists():
        shutil.rmtree(storage_root, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None, None, None]:
    yield
    with db_module.SessionLocal() as database:
        for table in reversed(Base.metadata.sorted_tables):
            database.execute(table.delete())
        database.commit()


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client
