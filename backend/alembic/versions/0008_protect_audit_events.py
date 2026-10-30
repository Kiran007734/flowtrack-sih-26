"""Restrict the runtime role to audit inserts.

Revision ID: 0008_protect_audit_events
Revises: 0007_compliance_validity
"""

import os
import re

from alembic import op

revision = "0008_protect_audit_events"
down_revision = "0007_compliance_validity"
branch_labels = None
depends_on = None


def _application_role() -> str:
    role = os.getenv("POSTGRES_APP_USER", "flowtrack_app")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", role):
        raise ValueError("POSTGRES_APP_USER must be a simple PostgreSQL identifier")
    return role


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    role = _application_role()
    op.execute(f'REVOKE UPDATE, DELETE ON TABLE audit_events FROM "{role}"')
    op.execute(f'GRANT INSERT, SELECT ON TABLE audit_events TO "{role}"')


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    role = _application_role()
    op.execute(f'GRANT UPDATE, DELETE ON TABLE audit_events TO "{role}"')
