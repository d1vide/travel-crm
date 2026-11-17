"""clients, request visibility and idempotency"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002_clients"
down_revision = "0001_auth"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public")
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_scope", sa.String(length=128), nullable=False),
        sa.Column("operation", sa.String(length=255), nullable=False),
        sa.Column("key", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("result_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_idempotency_records_valid_request_hash"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_records")),
        sa.UniqueConstraint(
            "actor_scope", "operation", "key", name="uq_idempotency_scope_operation_key"
        ),
    )
    op.create_table(
        "clients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "client_number", sa.Integer(), sa.Identity(always=False, start=1), nullable=False
        ),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("full_name_normalized", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("phone_normalized", sa.String(length=16), nullable=True),
        sa.Column("email_normalized", sa.Text(), nullable=True),
        sa.Column("preferences", sa.Text(), server_default="", nullable=False),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
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
            "phone_normalized IS NULL OR phone_normalized ~ '^\\+[0-9]{7,15}$'",
            name=op.f("ck_clients_phone_format"),
        ),
        sa.CheckConstraint(
            "(email IS NULL) = (email_normalized IS NULL)", name=op.f("ck_clients_email_pair")
        ),
        sa.CheckConstraint(
            "(phone IS NULL) = (phone_normalized IS NULL)", name=op.f("ck_clients_phone_pair")
        ),
        sa.CheckConstraint("client_number > 0", name=op.f("ck_clients_positive_number")),
        sa.CheckConstraint(
            "email_normalized IS NULL OR length(trim(email_normalized)) > 0",
            name=op.f("ck_clients_email_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(full_name)) > 0", name=op.f("ck_clients_full_name_not_blank")
        ),
        sa.CheckConstraint(
            "phone_normalized IS NOT NULL OR email_normalized IS NOT NULL",
            name=op.f("ck_clients_contact_required"),
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_clients_positive_version")),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_clients_created_by_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clients")),
        sa.UniqueConstraint("client_number", name=op.f("uq_clients_client_number")),
    )
    op.create_index("ix_clients_created_by_id", "clients", ["created_by_id"], unique=False)
    op.create_index("ix_clients_email_normalized", "clients", ["email_normalized"], unique=False)
    op.create_index(
        "ix_clients_full_name_trgm",
        "clients",
        ["full_name_normalized"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"full_name_normalized": "gin_trgm_ops"},
    )
    op.create_index("ix_clients_phone_normalized", "clients", ["phone_normalized"], unique=False)
    op.create_table(
        "requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("manager_id", sa.Uuid(), nullable=False),
        sa.Column("destination", sa.Text(), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("tourist_count", sa.Integer(), nullable=False),
        sa.Column("budget", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("wishes", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "new",
                "in_progress",
                "offer_prepared",
                "booked",
                "completed",
                "cancelled",
                name="request_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="new",
            nullable=False,
        ),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("budget >= 0", name=op.f("ck_requests_nonnegative_budget")),
        sa.CheckConstraint("ends_on >= starts_on", name=op.f("ck_requests_valid_dates")),
        sa.CheckConstraint("tourist_count > 0", name=op.f("ck_requests_positive_tourist_count")),
        sa.CheckConstraint("version > 0", name=op.f("ck_requests_positive_version")),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["clients.id"],
            name=op.f("fk_requests_client_id_clients"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["manager_id"],
            ["users.id"],
            name=op.f("fk_requests_manager_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requests")),
    )
    op.create_index("ix_requests_client_id", "requests", ["client_id"], unique=False)
    op.create_index("ix_requests_created_at", "requests", ["created_at"], unique=False)
    op.create_index(
        "ix_requests_manager_status_created",
        "requests",
        ["manager_id", "status", "created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_requests_manager_status_created", table_name="requests")
    op.drop_index("ix_requests_created_at", table_name="requests")
    op.drop_index("ix_requests_client_id", table_name="requests")
    op.drop_table("requests")
    op.drop_index("ix_clients_phone_normalized", table_name="clients")
    op.drop_index(
        "ix_clients_full_name_trgm",
        table_name="clients",
        postgresql_using="gin",
        postgresql_ops={"full_name_normalized": "gin_trgm_ops"},
    )
    op.drop_index("ix_clients_email_normalized", table_name="clients")
    op.drop_index("ix_clients_created_by_id", table_name="clients")
    op.drop_table("clients")
    op.drop_table("idempotency_records")
    # pg_trgm can be shared by other schemas; downgrading these tables leaves it installed.
