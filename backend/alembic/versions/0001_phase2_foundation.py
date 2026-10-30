"""Create the Phase 2 modular-monolith foundation schema.

Revision ID: 0001_phase2_foundation
Revises:
Create Date: 2026-10-27
"""

from alembic import op
from app.models import Base

revision = "0001_phase2_foundation"
down_revision = None
branch_labels = None
depends_on = None

# Freeze this initial revision's scope. New ORM models must be introduced by a
# later explicit migration, never by mutating the schema materialized here.
BASELINE_TABLE_NAMES = frozenset(
    {
        "application_stage_history",
        "application_versions",
        "applications",
        "audit_events",
        "auth_sessions",
        "document_versions",
        "documents",
        "institutions",
        "job_executions",
        "login_attempts",
        "notifications",
        "outbox_events",
        "permissions",
        "regions",
        "role_assignments",
        "role_permissions",
        "roles",
        "users",
        "workflow_stages",
        "workflow_template_versions",
        "workflow_templates",
        "workflow_transitions",
    }
)


def upgrade() -> None:
    # This initial revision deliberately materializes the typed SQLAlchemy 2 metadata
    # defined for the Phase 2 baseline. Subsequent revisions must contain explicit,
    # forward-only schema operations and must not mutate this revision.
    baseline_tables = [
        table for table in Base.metadata.sorted_tables if table.name in BASELINE_TABLE_NAMES
    ]
    Base.metadata.create_all(bind=op.get_bind(), tables=baseline_tables, checkfirst=True)


def downgrade() -> None:
    # Reverse order preserves foreign-key dependencies. Downgrades are for a local
    # disposable environment; production changes are forward-only by policy.
    bind = op.get_bind()
    for table in reversed(
        [table for table in Base.metadata.sorted_tables if table.name in BASELINE_TABLE_NAMES]
    ):
        table.drop(bind=bind, checkfirst=True)
