import sqlalchemy as sa
from alembic import op

revision = "0001_operations"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "operations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("client_operation_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("simulate_timeout", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("succeeded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_operations_positive_amount"),
        sa.CheckConstraint("currency = 'RUB'", name="ck_operations_currency"),
        sa.CheckConstraint(
            "status IN ('pending','succeeded','failed')", name="ck_operations_status"
        ),
        sa.CheckConstraint(
            "(status = 'succeeded') = (succeeded_at IS NOT NULL)",
            name="ck_operations_success_time",
        ),
    )


def downgrade():
    op.drop_table("operations")
