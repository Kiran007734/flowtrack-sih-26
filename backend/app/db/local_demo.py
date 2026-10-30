"""Create a new SQLite-backed synthetic demo only when Docker is unavailable.

This is deliberately not an Alembic substitute and must never be used for a
shared, production, or PostgreSQL validation environment. It creates the
current ORM schema, exactly as the host-only test fixture does, then runs the
guarded synthetic seed. Existing database files are never overwritten.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.db.seed import seed
from app.db.session import engine
from app.models import Base


def _sqlite_database_path(database_url: str) -> Path:
    url = make_url(database_url)
    if url.drivername != "sqlite+pysqlite" or not url.database or url.database == ":memory:":
        raise RuntimeError(
            "Local demo bootstrap requires a file-backed sqlite+pysqlite DATABASE_URL"
        )
    path = Path(url.database).resolve()
    backend_root = Path(__file__).resolve().parents[2]
    try:
        path.relative_to(backend_root)
    except ValueError as exc:
        raise RuntimeError(
            "Local demo database must be located inside the backend directory"
        ) from exc
    return path


def bootstrap_local_demo() -> dict[str, object]:
    settings = get_settings()
    if settings.environment != "development" or not settings.development_seed_enabled:
        raise RuntimeError(
            "Local demo bootstrap requires ENVIRONMENT=development and ENABLE_DEVELOPMENT_SEED=true"
        )
    database_path = _sqlite_database_path(settings.database_url)
    if database_path.exists():
        raise RuntimeError(
            f"Refusing to overwrite an existing local demo database: {database_path}"
        )
    database_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    return {"mode": "sqlite-local-demo-not-postgresql", "database": database_path.name, **seed()}


if __name__ == "__main__":
    print(json.dumps(bootstrap_local_demo(), sort_keys=True))
