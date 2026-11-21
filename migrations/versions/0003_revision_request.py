"""Pin revision base and detect conflicting idempotency-key reuse."""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"


def upgrade():
    op.add_column("report_versions", sa.Column("request_payload", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("report_versions", "request_payload")
