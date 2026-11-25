"""bookings"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0008_bookings"
down_revision = "0007_tourists"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_tourists_id_request", "tourists", ["id", "request_id"])
    op.create_table(
        "bookings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("selection_item_id", sa.Uuid(), nullable=False),
        sa.Column("offer_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("supplier_booking_number", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("cancellation_response", sa.Text(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL)",
            name=op.f("ck_bookings_cancellation_time"),
        ),
        sa.CheckConstraint(
            "(status = 'rejected') = (rejection_reason IS NOT NULL)",
            name=op.f("ck_bookings_rejection_reason"),
        ),
        sa.CheckConstraint(
            "(status IN ('pending_confirmation', 'rejected') AND supplier_booking_number IS NULL AND confirmed_at IS NULL) OR (status IN ('confirmed', 'cancellation_requested', 'cancelled') AND supplier_booking_number IS NOT NULL AND confirmed_at IS NOT NULL)",
            name=op.f("ck_bookings_confirmation_fields"),
        ),
        sa.CheckConstraint("currency = 'RUB'", name=op.f("ck_bookings_currency")),
        sa.CheckConstraint(
            "jsonb_typeof(offer_snapshot) = 'object' AND offer_snapshot ? 'price' AND offer_snapshot ? 'currency'",
            name=op.f("ck_bookings_snapshot_object"),
        ),
        sa.CheckConstraint(
            "rejection_reason IS NULL OR btrim(rejection_reason) <> ''",
            name=op.f("ck_bookings_nonblank_rejection"),
        ),
        sa.CheckConstraint(
            "status IN ('pending_confirmation', 'confirmed', 'rejected', 'cancellation_requested', 'cancelled')",
            name=op.f("ck_bookings_status"),
        ),
        sa.CheckConstraint(
            "supplier_booking_number IS NULL OR btrim(supplier_booking_number) <> ''",
            name=op.f("ck_bookings_nonblank_supplier_number"),
        ),
        sa.CheckConstraint(
            "COALESCE(total_amount = (offer_snapshot->>'price')::numeric AND offer_snapshot->>'currency' = currency, false)",
            name=op.f("ck_bookings_snapshot_price"),
        ),
        sa.CheckConstraint("total_amount >= 0", name=op.f("ck_bookings_nonnegative_amount")),
        sa.CheckConstraint("version > 0", name=op.f("ck_bookings_positive_version")),
        sa.ForeignKeyConstraint(
            ["selection_item_id", "request_id"],
            ["selection_items.id", "selection_items.request_id"],
            name="fk_bookings_item_request",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bookings")),
        sa.UniqueConstraint("id", "request_id", name="uq_bookings_id_request"),
    )
    op.create_index(
        "ix_bookings_request_created", "bookings", ["request_id", "created_at", "id"], unique=False
    )
    op.create_index(
        "uq_bookings_active_request",
        "bookings",
        ["request_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('pending_confirmation', 'confirmed', 'cancellation_requested')"
        ),
    )
    op.create_table(
        "booking_tourists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("tourist_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("tourist_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(tourist_snapshot) = 'object'",
            name=op.f("ck_booking_tourists_snapshot_object"),
        ),
        sa.CheckConstraint("position >= 0", name=op.f("ck_booking_tourists_nonnegative_position")),
        sa.ForeignKeyConstraint(
            ["booking_id", "request_id"],
            ["bookings.id", "bookings.request_id"],
            name="fk_booking_tourists_booking_request",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tourist_id", "request_id"],
            ["tourists.id", "tourists.request_id"],
            name="fk_booking_tourists_tourist_request",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_booking_tourists")),
        sa.UniqueConstraint("booking_id", "position", name="uq_booking_tourists_position"),
        sa.UniqueConstraint("booking_id", "tourist_id", name="uq_booking_tourists_tourist"),
    )


def downgrade():
    op.drop_table("booking_tourists")
    op.drop_constraint("uq_tourists_id_request", "tourists", type_="unique")
    op.drop_index(
        "uq_bookings_active_request",
        table_name="bookings",
        postgresql_where=sa.text(
            "status IN ('pending_confirmation', 'confirmed', 'cancellation_requested')"
        ),
    )
    op.drop_index("ix_bookings_request_created", table_name="bookings")
    op.drop_table("bookings")
