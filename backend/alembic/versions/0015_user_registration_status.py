"""add user registration status"""

from alembic import op
import sqlalchemy as sa

revision = "0015_user_registration_status"
down_revision = "0014_decisions_communications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("registration_status", sa.String(length=32), nullable=False, server_default="APPROVED"))
    op.create_check_constraint("ck_user_registration_status", "users", "registration_status IN ('PENDING', 'APPROVED', 'REJECTED')")
    op.alter_column("users", "registration_status", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_user_registration_status", "users", type_="check")
    op.drop_column("users", "registration_status")
