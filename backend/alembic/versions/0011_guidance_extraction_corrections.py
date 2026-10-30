"""Preserve reviewer revisions of guidance extraction text.

Revision ID: 0011_guidance_extraction_corrections
Revises: 0010_guidance_ocr
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_guidance_extraction_corrections"
down_revision = "0010_guidance_ocr"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guidance_extraction_corrections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "page_id",
            sa.Uuid(),
            sa.ForeignKey("guidance_extraction_pages.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("corrected_text", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "corrected_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("page_id", "revision_number", name="uq_guidance_extraction_correction"),
    )
    op.create_index(
        "ix_guidance_extraction_correction_page",
        "guidance_extraction_corrections",
        ["page_id", "revision_number"],
    )


def downgrade() -> None:
    op.drop_table("guidance_extraction_corrections")
