"""Persist completed authenticated command responses for idempotent replay.

Revision ID: 0002_command_idempotency
Revises: 0001_phase2_foundation
Create Date: 2026-10-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_command_idempotency"
down_revision = "0001_phase2_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "command_idempotency",
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=160), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", sa.JSON(), nullable=False),
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
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "actor_id", "operation", "idempotency_key", name="uq_command_idempotency"
        ),
    )
    op.create_index(
        "ix_command_idempotency_actor_operation",
        "command_idempotency",
        ["actor_id", "operation"],
        unique=False,
    )
    op.create_index(
        "ix_command_idempotency_actor_id", "command_idempotency", ["actor_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_command_idempotency_actor_id", table_name="command_idempotency")
    op.drop_index("ix_command_idempotency_actor_operation", table_name="command_idempotency")
    op.drop_table("command_idempotency")
