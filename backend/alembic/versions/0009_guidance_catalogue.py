"""Add versioned guidance, requirement catalogue and reviewed evidence mappings.

Revision ID: 0009_guidance_catalogue
Revises: 0008_protect_audit_events
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_guidance_catalogue"
down_revision = "0008_protect_audit_events"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "guidance_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.String(96), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("issuing_organization", sa.String(255)),
        sa.Column("source_reference", sa.String(1024)),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        *_timestamps(),
    )
    op.create_index("ix_guidance_sources_key", "guidance_sources", ["key"])
    op.create_table(
        "guidance_source_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("guidance_sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("version_label", sa.String(128), nullable=False),
        sa.Column("effective_date", sa.DateTime(timezone=True)),
        sa.Column("content_hash", sa.String(128)),
        sa.Column("upload_metadata", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("verification_status", sa.String(48), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reviewed_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.UniqueConstraint("source_id", "version_number", name="uq_guidance_source_version"),
    )
    op.create_index(
        "ix_guidance_source_version_status",
        "guidance_source_versions",
        ["status", "verification_status"],
    )
    op.create_table(
        "catalogue_requirements",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("stable_identifier", sa.String(128), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "source_version_id",
            sa.Uuid(),
            sa.ForeignKey("guidance_source_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("module_key", sa.String(64), nullable=False),
        sa.Column("section_reference", sa.String(255)),
        sa.Column("applicability_conditions", sa.JSON(), nullable=False),
        sa.Column("evidence_metadata", sa.JSON(), nullable=False),
        sa.Column("severity", sa.String(32)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reviewed_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "supersedes_requirement_id",
            sa.Uuid(),
            sa.ForeignKey("catalogue_requirements.id", ondelete="RESTRICT"),
        ),
        *_timestamps(),
        sa.UniqueConstraint(
            "stable_identifier", "version_number", name="uq_catalogue_requirement_version"
        ),
    )
    op.create_index(
        "ix_catalogue_requirement_filter",
        "catalogue_requirements",
        ["source_version_id", "category", "module_key", "status"],
    )
    op.create_table(
        "requirement_evidence_mappings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "requirement_id",
            sa.Uuid(),
            sa.ForeignKey("catalogue_requirements.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "application_id",
            sa.Uuid(),
            sa.ForeignKey("applications.id", ondelete="RESTRICT"),
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
        sa.Column(
            "evc_evidence_link_id",
            sa.Uuid(),
            sa.ForeignKey("evc_evidence_links.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "compliance_evidence_id",
            sa.Uuid(),
            sa.ForeignKey("compliance_evidence.id", ondelete="RESTRICT"),
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("mapping_method", sa.String(48), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reviewed_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_reason", sa.Text()),
        sa.Column(
            "supersedes_mapping_id",
            sa.Uuid(),
            sa.ForeignKey("requirement_evidence_mappings.id", ondelete="RESTRICT"),
        ),
        *_timestamps(),
    )
    op.create_index(
        "ix_requirement_mapping_requirement_status",
        "requirement_evidence_mappings",
        ["requirement_id", "status"],
    )
    op.create_index(
        "ix_requirement_mapping_application",
        "requirement_evidence_mappings",
        ["application_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("requirement_evidence_mappings")
    op.drop_table("catalogue_requirements")
    op.drop_table("guidance_source_versions")
    op.drop_table("guidance_sources")
