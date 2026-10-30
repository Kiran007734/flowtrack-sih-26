"""Idempotently upgrade the guarded SQLite demonstration schema.

This is deliberately separate from Alembic: the demonstration fallback is
created from ORM metadata and earlier PostgreSQL migrations are not SQLite
compatible. It only supports explicitly named, file-backed SQLite databases
inside the backend directory and never recreates or resets data.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def _database_path(raw_path: str) -> Path:
    path = Path(raw_path).resolve()
    backend_root = Path(__file__).resolve().parents[2]
    try:
        path.relative_to(backend_root)
    except ValueError as exc:
        raise RuntimeError("SQLite upgrade target must be inside the backend directory") from exc
    if not path.is_file() or path.suffix != ".sqlite3":
        raise RuntimeError("SQLite upgrade target must be an existing .sqlite3 file")
    return path


def upgrade_registration_status(raw_path: str) -> str:
    """Add the Phase 1 state column while preserving every existing row."""

    path = _database_path(raw_path)
    with sqlite3.connect(path, timeout=15) as database:
        database.execute("PRAGMA foreign_keys = ON")
        columns = {row[1] for row in database.execute("PRAGMA table_info(users)")}
        if "registration_status" in columns:
            return "already_current"
        database.execute("BEGIN IMMEDIATE")
        try:
            database.execute(
                "ALTER TABLE users ADD COLUMN registration_status "
                "TEXT NOT NULL DEFAULT 'APPROVED'"
            )
            database.commit()
        except Exception:
            database.rollback()
            raise
    return "upgraded"


def main() -> None:
    parser = argparse.ArgumentParser(description="Upgrade a guarded FlowTrack SQLite local demo")
    parser.add_argument(
        "--database", required=True, help="Existing backend-local .sqlite3 database"
    )
    args = parser.parse_args()
    print(upgrade_registration_status(args.database))


if __name__ == "__main__":
    main()
