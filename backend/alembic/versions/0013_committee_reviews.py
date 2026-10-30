# ruff: noqa: E501
"""Add configurable committee review lifecycle.

Revision ID: 0013_committee_reviews
Revises: 0012_guidance_passages
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_committee_reviews"
down_revision = "0012_guidance_passages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "committee_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "application_id",
            sa.Uuid(),
            sa.ForeignKey("applications.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "workflow_template_version_id",
            sa.Uuid(),
            sa.ForeignKey("workflow_template_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("stage_key", sa.String(96), nullable=False),
        sa.Column("committee_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("meeting_metadata", sa.JSON(), nullable=False),
        sa.Column("outcome", sa.String(32)),
        sa.Column("outcome_reason", sa.Text()),
        sa.Column(
            "finalized_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")
        ),
        sa.Column("finalized_at", sa.DateTime(timezone=True)),
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
    )
    op.create_index(
        "ix_committee_review_application", "committee_reviews", ["application_id", "status"]
    )
    op.create_table(
        "committee_review_members",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "committee_review_id",
            sa.Uuid(),
            sa.ForeignKey("committee_reviews.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "assigned_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
        sa.UniqueConstraint("committee_review_id", "user_id", name="uq_committee_member"),
    )
    op.create_table(
        "committee_member_submissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "committee_review_id",
            sa.Uuid(),
            sa.ForeignKey("committee_reviews.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "member_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("recommendation", sa.String(32), nullable=False),
        sa.Column("findings", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.UniqueConstraint("committee_review_id", "member_id", name="uq_committee_submission"),
    )


def downgrade() -> None:
    op.drop_table("committee_member_submissions")
    op.drop_table("committee_review_members")
    op.drop_table("committee_reviews")
