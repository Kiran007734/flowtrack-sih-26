"""Add EVC evidence links and checklist/report lifecycle metadata.

Revision ID: 0006_evc_evidence_and_report_lifecycle
Revises: 0005_evc_visits
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_evc_evidence_and_report_lifecycle"
down_revision = "0005_evc_visits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evc_checklist_items", sa.Column("completed_by_user_id", sa.Uuid()))
    op.add_column("evc_checklist_items", sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.create_foreign_key(
        "fk_evc_checklist_completed_by",
        "evc_checklist_items",
        "users",
        ["completed_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column("evc_reports", sa.Column("return_reason", sa.Text()))
    op.create_table(
        "evc_evidence_links",
        sa.Column("visit_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("verified_by_user_id", sa.Uuid()),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
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
        sa.ForeignKeyConstraint(["visit_id"], ["evc_visits.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("visit_id", "document_id", "purpose", name="uq_evc_evidence_link"),
    )


def downgrade() -> None:
    op.drop_table("evc_evidence_links")
