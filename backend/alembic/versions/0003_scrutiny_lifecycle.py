"""Add synthetic scrutiny review and deficiency traceability.

Revision ID: 0003_scrutiny_lifecycle
Revises: 0002_command_idempotency
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_scrutiny_lifecycle"
down_revision = "0002_command_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scrutiny_reviews",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_id", "reviewer_id", name="uq_scrutiny_review_reviewer"),
    )
    op.create_index(
        "ix_scrutiny_review_application_status", "scrutiny_reviews", ["application_id", "status"]
    )
    op.create_index("ix_scrutiny_reviews_application_id", "scrutiny_reviews", ["application_id"])
    op.create_index("ix_scrutiny_reviews_reviewer_id", "scrutiny_reviews", ["reviewer_id"])
    op.create_table(
        "scrutiny_findings",
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_reference", sa.String(255), nullable=False),
        sa.Column("assessment", sa.String(32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("references", sa.JSON(), nullable=False),
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
        sa.ForeignKeyConstraint(["review_id"], ["scrutiny_reviews.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scrutiny_findings_review_id", "scrutiny_findings", ["review_id"])
    op.create_table(
        "deficiencies",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid()),
        sa.Column("identifier", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("raised_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by_user_id", sa.Uuid()),
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
        sa.ForeignKeyConstraint(["finding_id"], ["scrutiny_findings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["raised_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("identifier", name="uq_deficiency_identifier"),
    )
    op.create_index(
        "ix_deficiency_application_status", "deficiencies", ["application_id", "status"]
    )
    op.create_index("ix_deficiencies_application_id", "deficiencies", ["application_id"])
    op.create_index("ix_deficiencies_finding_id", "deficiencies", ["finding_id"])
    op.create_table(
        "deficiency_responses",
        sa.Column("deficiency_id", sa.Uuid(), nullable=False),
        sa.Column("responder_id", sa.Uuid(), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Uuid()),
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
        sa.ForeignKeyConstraint(["deficiency_id"], ["deficiencies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["responder_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_deficiency_responses_deficiency_id", "deficiency_responses", ["deficiency_id"]
    )


def downgrade() -> None:
    op.drop_table("deficiency_responses")
    op.drop_table("deficiencies")
    op.drop_table("scrutiny_findings")
    op.drop_table("scrutiny_reviews")
