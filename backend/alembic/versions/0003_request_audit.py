"""request audit history"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_request_audit"
down_revision = "0002_clients"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "audit_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "entity_type IN ('request', 'booking', 'payment', 'refund')",
            name=op.f("ck_audit_records_entity_type"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(changes) = 'array'", name=op.f("ck_audit_records_changes_array")
        ),
        sa.CheckConstraint(
            "source IN ('staff', 'payment_service', 'system')", name=op.f("ck_audit_records_source")
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_audit_records_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["requests.id"],
            name=op.f("fk_audit_records_request_id_requests"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_records")),
    )
    op.create_index(
        "ix_audit_records_request_created",
        "audit_records",
        ["request_id", "created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_audit_records_request_created", table_name="audit_records")
    op.drop_table("audit_records")
