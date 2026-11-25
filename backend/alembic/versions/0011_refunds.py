"""refunds"""

import sqlalchemy as sa

from alembic import op

revision = "0011_refunds"
down_revision = "0010_reconciliation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "refunds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column(
            "next_reconcile_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("external_operation_id", sa.String(length=64), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("pending_reason", sa.Text(), nullable=True),
        sa.Column("succeeded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_conflict", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'failed') = (failure_reason IS NOT NULL)",
            name=op.f("ck_refunds_failure_reason"),
        ),
        sa.CheckConstraint(
            "(status = 'succeeded') = (succeeded_at IS NOT NULL)",
            name=op.f("ck_refunds_success_time"),
        ),
        sa.CheckConstraint("currency = 'RUB'", name=op.f("ck_refunds_currency")),
        sa.CheckConstraint(
            "status = 'processing' OR external_operation_id IS NOT NULL",
            name=op.f("ck_refunds_terminal_operation"),
        ),
        sa.CheckConstraint(
            "status = 'processing' OR pending_reason IS NULL",
            name=op.f("ck_refunds_pending_reason"),
        ),
        sa.CheckConstraint(
            "status IN ('processing','succeeded','failed')", name=op.f("ck_refunds_status")
        ),
        sa.CheckConstraint("amount > 0", name=op.f("ck_refunds_positive_amount")),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.id"],
            name=op.f("fk_refunds_payment_id_payments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refunds")),
        sa.UniqueConstraint(
            "provider", "external_operation_id", name="uq_refunds_provider_operation"
        ),
    )
    op.create_index("ix_refunds_created", "refunds", ["created_at", "id"], unique=False)
    op.create_index("ix_refunds_payment_status", "refunds", ["payment_id", "status"], unique=False)
    op.create_index(
        "ix_refunds_processing_reconcile",
        "refunds",
        ["next_reconcile_at", "id"],
        unique=False,
        postgresql_where=sa.text("status = 'processing'"),
    )


def downgrade():
    op.drop_index(
        "ix_refunds_processing_reconcile",
        table_name="refunds",
        postgresql_where=sa.text("status = 'processing'"),
    )
    op.drop_index("ix_refunds_payment_status", table_name="refunds")
    op.drop_index("ix_refunds_created", table_name="refunds")
    op.drop_table("refunds")
