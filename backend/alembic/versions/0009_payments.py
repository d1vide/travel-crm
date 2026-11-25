"""payments"""

import sqlalchemy as sa

from alembic import op

revision = "0009_payments"
down_revision = "0008_bookings"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_operation_id", sa.String(length=64), nullable=True),
        sa.Column("payment_url", sa.Text(), nullable=True),
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
            name=op.f("ck_payments_failure_reason"),
        ),
        sa.CheckConstraint(
            "(status = 'succeeded') = (succeeded_at IS NOT NULL)",
            name=op.f("ck_payments_success_time"),
        ),
        sa.CheckConstraint("currency = 'RUB'", name=op.f("ck_payments_currency")),
        sa.CheckConstraint(
            "status = 'pending' OR external_operation_id IS NOT NULL",
            name=op.f("ck_payments_terminal_operation"),
        ),
        sa.CheckConstraint(
            "status = 'pending' OR pending_reason IS NULL", name=op.f("ck_payments_pending_reason")
        ),
        sa.CheckConstraint(
            "status IN ('pending','succeeded','failed')", name=op.f("ck_payments_status")
        ),
        sa.CheckConstraint("amount > 0", name=op.f("ck_payments_positive_amount")),
        sa.ForeignKeyConstraint(
            ["booking_id"],
            ["bookings.id"],
            name=op.f("fk_payments_booking_id_bookings"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        sa.UniqueConstraint(
            "provider", "external_operation_id", name="uq_payments_provider_operation"
        ),
    )
    op.create_index(
        "ix_payments_booking_status", "payments", ["booking_id", "status"], unique=False
    )
    op.create_index("ix_payments_created", "payments", ["created_at", "id"], unique=False)
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint("type = 'payment_succeeded'", name=op.f("ck_notifications_type")),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.id"],
            name=op.f("fk_notifications_payment_id_payments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"],
            ["users.id"],
            name=op.f("fk_notifications_recipient_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint(
            "recipient_id", "payment_id", "type", name="uq_notifications_recipient_payment_type"
        ),
    )
    op.create_index(
        "ix_notifications_recipient_created",
        "notifications",
        ["recipient_id", "created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_notifications_recipient_created", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_payments_created", table_name="payments")
    op.drop_index("ix_payments_booking_status", table_name="payments")
    op.drop_table("payments")
