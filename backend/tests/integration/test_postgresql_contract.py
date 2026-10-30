from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text


@pytest.mark.integration
def test_real_postgresql_is_explicitly_required_for_critical_semantics() -> None:
    """Reserve an explicit real-PostgreSQL suite; host has no Docker/PostgreSQL service."""

    database_url = os.getenv("TEST_POSTGRES_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRES_DATABASE_URL is not configured on this host")
    assert database_url.startswith("postgresql")
    engine = create_engine(database_url)
    with engine.connect() as connection:
        grants = connection.execute(
            text(
                "SELECT has_table_privilege(current_user, 'audit_events', 'INSERT'), "
                "has_table_privilege(current_user, 'audit_events', 'UPDATE'), "
                "has_table_privilege(current_user, 'audit_events', 'DELETE')"
            )
        ).one()
    assert grants == (True, False, False)
