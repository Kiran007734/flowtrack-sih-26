"""Add application-specific synthetic reviewer assignments.

Revision ID: 0004_reviewer_assignments
Revises: 0003_scrutiny_lifecycle
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_reviewer_assignments"
down_revision = "0003_scrutiny_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reviewer_assignments",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("responsibility", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("reason", sa.Text()),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_reviewer_assignment_application_status",
        "reviewer_assignments",
        ["application_id", "status"],
    )
    op.create_index(
        "ix_reviewer_assignment_reviewer_status", "reviewer_assignments", ["reviewer_id", "status"]
    )
    op.create_index(
        "ix_reviewer_assignments_application_id", "reviewer_assignments", ["application_id"]
    )
    op.create_index("ix_reviewer_assignments_reviewer_id", "reviewer_assignments", ["reviewer_id"])


def downgrade() -> None:
    op.drop_table("reviewer_assignments")
