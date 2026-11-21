"""Distinguish repeated actions from legitimate evidence pagination."""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"


def upgrade():
    op.add_column(
        "runs", sa.Column("last_action_signature", sa.String(64), nullable=False, server_default="")
    )


def downgrade():
    op.drop_column("runs", "last_action_signature")
