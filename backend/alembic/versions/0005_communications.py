"""client communications"""

import sqlalchemy as sa

from alembic import op

revision = "0005_communications"
down_revision = "0004_tour_catalogue"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_requests_id_client", "requests", ["id", "client_id"])
    op.create_table(
        "communications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column(
            "channel",
            sa.Enum(
                "phone",
                "email",
                "messenger",
                "office",
                "other",
                name="communication_channel",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("length(trim(text)) > 0", name=op.f("ck_communications_text_not_blank")),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_communications_author_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["clients.id"],
            name=op.f("fk_communications_client_id_clients"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["request_id", "client_id"],
            ["requests.id", "requests.client_id"],
            name="fk_communications_request_client",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_communications")),
    )
    op.create_index(
        "ix_communications_client_occurred",
        "communications",
        ["client_id", "occurred_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_communications_request_occurred",
        "communications",
        ["request_id", "occurred_at", "id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_communications_request_occurred", table_name="communications")
    op.drop_index("ix_communications_client_occurred", table_name="communications")
    op.drop_table("communications")
    op.drop_constraint("uq_requests_id_client", "requests", type_="unique")
