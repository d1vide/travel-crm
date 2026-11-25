import sqlalchemy as sa
from alembic import op

revision = "0002_delivery"
down_revision = "0001_operations"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "operations",
        sa.Column("delivery_pending", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "operations",
        sa.Column(
            "next_delivery_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
    )
    op.create_index(
        "ix_operations_delivery",
        "operations",
        ["next_delivery_at", "id"],
        postgresql_where=sa.text("delivery_pending"),
    )
    op.execute(
        "UPDATE operations SET delivery_pending = true WHERE status IN ('succeeded', 'failed')"
    )


def downgrade():
    op.drop_index("ix_operations_delivery", table_name="operations")
    op.drop_column("operations", "next_delivery_at")
    op.drop_column("operations", "delivery_pending")
