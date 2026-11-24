"""tourists"""

import sqlalchemy as sa

from alembic import op

revision = "0007_tourists"
down_revision = "0006_selections"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tourists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=False),
        sa.Column("document_type", sa.Text(), nullable=False),
        sa.Column("document_number", sa.Text(), nullable=False),
        sa.Column("document_expires_on", sa.Date(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
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
            "birth_date <= (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Moscow')::date",
            name=op.f("ck_tourists_birth_not_future"),
        ),
        sa.CheckConstraint(
            "btrim(document_number) <> ''", name=op.f("ck_tourists_nonblank_document")
        ),
        sa.CheckConstraint("btrim(full_name) <> ''", name=op.f("ck_tourists_nonblank_name")),
        sa.CheckConstraint(
            "document_type <> 'international_passport' OR document_expires_on IS NOT NULL",
            name=op.f("ck_tourists_international_expiry"),
        ),
        sa.CheckConstraint(
            "document_type IN ('passport', 'international_passport')",
            name=op.f("ck_tourists_document_type"),
        ),
        sa.CheckConstraint("position >= 0", name=op.f("ck_tourists_nonnegative_position")),
        sa.CheckConstraint("version > 0", name=op.f("ck_tourists_positive_version")),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["requests.id"],
            name=op.f("fk_tourists_request_id_requests"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tourists")),
    )
    op.create_index(
        "ix_tourists_request_position", "tourists", ["request_id", "position"], unique=False
    )


def downgrade():
    op.drop_index("ix_tourists_request_position", table_name="tourists")
    op.drop_table("tourists")
