"""payment reconciliation"""

import sqlalchemy as sa

from alembic import op

revision = "0010_reconciliation"
down_revision = "0009_payments"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "payments",
        sa.Column(
            "next_reconcile_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_payments_pending_reconcile",
        "payments",
        ["next_reconcile_at", "id"],
        unique=False,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade():
    op.drop_index(
        "ix_payments_pending_reconcile",
        table_name="payments",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_column("payments", "next_reconcile_at")
