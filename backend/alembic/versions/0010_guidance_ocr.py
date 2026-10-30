"""Add private guidance ingestion runs and page extraction provenance.

Revision ID: 0010_guidance_ocr
Revises: 0009_guidance_catalogue
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_guidance_ocr"
down_revision = "0009_guidance_catalogue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guidance_source_versions", sa.Column("original_document_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "guidance_source_versions",
        sa.Column("original_document_version_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "guidance_source_versions",
        sa.Column("ingestion_status", sa.String(32), nullable=False, server_default="NOT_STARTED"),
    )
    op.create_foreign_key(
        "fk_guidance_version_document",
        "guidance_source_versions",
        "documents",
        ["original_document_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_guidance_version_document_version",
        "guidance_source_versions",
        "document_versions",
        ["original_document_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_table(
        "guidance_extraction_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_version_id",
            sa.Uuid(),
            sa.ForeignKey("guidance_source_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            sa.Uuid(),
            sa.ForeignKey("document_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("extractor_name", sa.String(96), nullable=False),
        sa.Column("extractor_version", sa.String(96)),
        sa.Column("source_file_hash", sa.String(128), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("failure_category", sa.String(96)),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("review_reason", sa.Text()),
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
        sa.UniqueConstraint(
            "source_version_id", "attempt_number", name="uq_guidance_extraction_attempt"
        ),
    )
    op.create_index(
        "ix_guidance_extraction_source_status",
        "guidance_extraction_runs",
        ["source_version_id", "status"],
    )
    op.create_table(
        "guidance_extraction_pages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("guidance_extraction_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("corrected_text", sa.Text()),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("quality_metadata", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column(
            "corrected_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")
        ),
        sa.Column("corrected_at", sa.DateTime(timezone=True)),
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
        sa.UniqueConstraint("run_id", "page_number", name="uq_guidance_extraction_page"),
    )
    op.create_index(
        "ix_guidance_extraction_page_run", "guidance_extraction_pages", ["run_id", "page_number"]
    )


def downgrade() -> None:
    op.drop_table("guidance_extraction_pages")
    op.drop_table("guidance_extraction_runs")
