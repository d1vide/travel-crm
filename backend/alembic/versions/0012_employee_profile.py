"""employee profile"""

import sqlalchemy as sa

from alembic import op

revision = "0012_employee_profile"
down_revision = "0011_refunds"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("department", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("position", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("work_phone", sa.String(64), nullable=True))


def downgrade():
    op.drop_column("users", "work_phone")
    op.drop_column("users", "position")
    op.drop_column("users", "department")
