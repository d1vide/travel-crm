import sqlalchemy as sa
from alembic import op

revision = "0003_refunds"
down_revision = "0002_delivery"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "refund_operations",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("client_operation_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column(
            "payment_id",
            sa.Uuid(),
            sa.ForeignKey("operations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("simulate_timeout", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("succeeded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_refund_operations_positive_amount"),
        sa.CheckConstraint("currency = 'RUB'", name="ck_refund_operations_currency"),
        sa.CheckConstraint(
            "status IN ('processing','succeeded','failed')", name="ck_refund_operations_status"
        ),
        sa.CheckConstraint(
            "(status = 'succeeded') = (succeeded_at IS NOT NULL)",
            name="ck_refund_operations_success_time",
        ),
    )
    op.create_index(
        "ix_refund_operations_payment_status", "refund_operations", ["payment_id", "status"]
    )


def downgrade():
    op.drop_index("ix_refund_operations_payment_status", table_name="refund_operations")
    op.drop_table("refund_operations")
