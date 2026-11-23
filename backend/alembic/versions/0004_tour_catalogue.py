"""tour catalogue"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004_tour_catalogue"
down_revision = "0003_request_audit"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tour_offers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("destination", sa.Text(), nullable=False),
        sa.Column("destination_normalized", sa.Text(), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("tourist_count", sa.Integer(), nullable=False),
        sa.Column("supplier", sa.Text(), nullable=False),
        sa.Column(
            "services",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.Text(), server_default="RUB", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "coalesce(array_ndims(services), 1) = 1 AND array_position(services, NULL) IS NULL AND array_position(services, '') IS NULL",
            name=op.f("ck_tour_offers_valid_services"),
        ),
        sa.CheckConstraint("currency = 'RUB'", name=op.f("ck_tour_offers_ruble_currency")),
        sa.CheckConstraint("ends_on >= starts_on", name=op.f("ck_tour_offers_valid_dates")),
        sa.CheckConstraint(
            "length(trim(destination)) > 0", name=op.f("ck_tour_offers_destination_not_blank")
        ),
        sa.CheckConstraint(
            "length(trim(destination_normalized)) > 0",
            name=op.f("ck_tour_offers_normalized_destination_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(supplier)) > 0", name=op.f("ck_tour_offers_supplier_not_blank")
        ),
        sa.CheckConstraint("length(trim(title)) > 0", name=op.f("ck_tour_offers_title_not_blank")),
        sa.CheckConstraint("price >= 0", name=op.f("ck_tour_offers_nonnegative_price")),
        sa.CheckConstraint("tourist_count > 0", name=op.f("ck_tour_offers_positive_tourist_count")),
        sa.CheckConstraint("version > 0", name=op.f("ck_tour_offers_positive_version")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tour_offers")),
    )
    op.create_index(
        "ix_tour_offers_active_destination",
        "tour_offers",
        ["destination_normalized"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"destination_normalized": "gin_trgm_ops"},
        postgresql_where=sa.text("is_active"),
    )
    op.create_index(
        "ix_tour_offers_active_filters",
        "tour_offers",
        ["tourist_count", "starts_on", "price"],
        unique=False,
        postgresql_where=sa.text("is_active"),
    )


def downgrade():
    op.drop_index(
        "ix_tour_offers_active_filters",
        table_name="tour_offers",
        postgresql_where=sa.text("is_active"),
    )
    op.drop_index(
        "ix_tour_offers_active_destination",
        table_name="tour_offers",
        postgresql_using="gin",
        postgresql_ops={"destination_normalized": "gin_trgm_ops"},
        postgresql_where=sa.text("is_active"),
    )
    op.drop_table("tour_offers")
