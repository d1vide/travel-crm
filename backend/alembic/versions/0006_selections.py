"""tour selections and public links"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0006_selections"
down_revision = "0005_communications"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "selections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_selections_created_by_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["requests.id"],
            name=op.f("fk_selections_request_id_requests"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_selections")),
        sa.UniqueConstraint("id", "request_id", name="uq_selections_id_request"),
    )
    op.create_index(
        "ix_selections_request_created",
        "selections",
        ["request_id", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "public_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("selection_id", sa.Uuid(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(purpose = 'selection' AND selection_id IS NOT NULL AND request_id IS NULL) OR (purpose = 'tourists' AND request_id IS NOT NULL AND selection_id IS NULL)",
            name=op.f("ck_public_links_purpose_target"),
        ),
        sa.CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_public_links_valid_token_hash")
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_public_links_positive_lifetime")
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_public_links_created_by_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["requests.id"],
            name=op.f("fk_public_links_request_id_requests"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["selection_id"],
            ["selections.id"],
            name=op.f("fk_public_links_selection_id_selections"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_public_links")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_public_links_token_hash")),
    )
    op.create_index(
        "uq_public_links_live_request",
        "public_links",
        ["request_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL AND purpose = 'tourists'"),
    )
    op.create_index(
        "uq_public_links_live_selection",
        "public_links",
        ["selection_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL AND purpose = 'selection'"),
    )
    op.create_table(
        "selection_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("selection_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("tour_offer_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("offer_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(offer_snapshot) = 'object'",
            name=op.f("ck_selection_items_snapshot_object"),
        ),
        sa.CheckConstraint("position >= 0", name=op.f("ck_selection_items_nonnegative_position")),
        sa.ForeignKeyConstraint(
            ["selection_id", "request_id"],
            ["selections.id", "selections.request_id"],
            name="fk_selection_items_selection_request",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tour_offer_id"],
            ["tour_offers.id"],
            name=op.f("fk_selection_items_tour_offer_id_tour_offers"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_selection_items")),
        sa.UniqueConstraint("id", "request_id", name="uq_selection_items_id_request"),
        sa.UniqueConstraint("selection_id", "position", name="uq_selection_items_position"),
        sa.UniqueConstraint("selection_id", "tour_offer_id", name="uq_selection_items_offer"),
    )
    op.add_column("requests", sa.Column("selected_selection_item_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_requests_selected_item_request",
        "requests",
        "selection_items",
        ["selected_selection_item_id", "id"],
        ["id", "request_id"],
        ondelete="RESTRICT",
        use_alter=True,
    )


def downgrade():
    op.drop_constraint("fk_requests_selected_item_request", "requests", type_="foreignkey")
    op.drop_column("requests", "selected_selection_item_id")
    op.drop_table("selection_items")
    op.drop_index(
        "uq_public_links_live_selection",
        table_name="public_links",
        postgresql_where=sa.text("revoked_at IS NULL AND purpose = 'selection'"),
    )
    op.drop_index(
        "uq_public_links_live_request",
        table_name="public_links",
        postgresql_where=sa.text("revoked_at IS NULL AND purpose = 'tourists'"),
    )
    op.drop_table("public_links")
    op.drop_index("ix_selections_request_created", table_name="selections")
    op.drop_table("selections")
