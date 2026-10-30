# ruff: noqa: E501
"""Add traceable guidance passages for retrieval.

Revision ID: 0012_guidance_passages
Revises: 0011_guidance_extraction_corrections
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_guidance_passages"
down_revision = "0011_guidance_extraction_corrections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guidance_passages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("guidance_sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_version_id",
            sa.Uuid(),
            sa.ForeignKey("guidance_source_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "extraction_run_id",
            sa.Uuid(),
            sa.ForeignKey("guidance_extraction_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "extraction_page_id",
            sa.Uuid(),
            sa.ForeignKey("guidance_extraction_pages.id", ondelete="RESTRICT"),
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
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("chunk_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("chunking_strategy", sa.String(64), nullable=False),
        sa.Column("index_version", sa.Integer(), nullable=False),
        sa.Column("embedding_model", sa.String(128)),
        sa.Column("embedding_status", sa.String(32), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
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
            "extraction_page_id", "chunk_number", "index_version", name="uq_guidance_passage"
        ),
    )
    op.create_index(
        "ix_guidance_passage_active", "guidance_passages", ["source_version_id", "is_active"]
    )


def downgrade() -> None:
    op.drop_table("guidance_passages")
