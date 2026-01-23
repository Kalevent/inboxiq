"""Add server defaults for timestamps and seat counts."""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
# Keep revision length <= 32 to satisfy alembic_version column.
revision = "20251206_acct_defaults_v1"
down_revision = "e037a9a806a7"
branch_labels = None
depends_on = None


def upgrade():
    # Backfill any existing nulls, then add server defaults.
    op.execute("UPDATE accounts SET created_at = NOW() WHERE created_at IS NULL;")
    op.execute("UPDATE accounts SET updated_at = NOW() WHERE updated_at IS NULL;")
    op.execute("UPDATE users SET created_at = NOW() WHERE created_at IS NULL;")
    op.execute("UPDATE users SET updated_at = NOW() WHERE updated_at IS NULL;")

    op.alter_column(
        "accounts",
        "created_at",
        server_default=sa.text("NOW()"),
        existing_type=sa.DateTime(),
    )
    op.alter_column(
        "accounts",
        "updated_at",
        server_default=sa.text("NOW()"),
        existing_type=sa.DateTime(),
    )
    op.alter_column(
        "accounts",
        "seats_limit",
        server_default=sa.text("1"),
        existing_type=sa.Integer(),
    )
    op.alter_column(
        "accounts",
        "seats_used",
        server_default=sa.text("0"),
        existing_type=sa.Integer(),
    )

    op.alter_column(
        "users",
        "created_at",
        server_default=sa.text("NOW()"),
        existing_type=sa.DateTime(),
    )
    op.alter_column(
        "users",
        "updated_at",
        server_default=sa.text("NOW()"),
        existing_type=sa.DateTime(),
    )


def downgrade():
    # Remove server defaults (keep data intact).
    op.alter_column(
        "users",
        "updated_at",
        server_default=None,
        existing_type=sa.DateTime(),
    )
    op.alter_column(
        "users",
        "created_at",
        server_default=None,
        existing_type=sa.DateTime(),
    )
    op.alter_column(
        "accounts",
        "seats_used",
        server_default=None,
        existing_type=sa.Integer(),
    )
    op.alter_column(
        "accounts",
        "seats_limit",
        server_default=None,
        existing_type=sa.Integer(),
    )
    op.alter_column(
        "accounts",
        "updated_at",
        server_default=None,
        existing_type=sa.DateTime(),
    )
    op.alter_column(
        "accounts",
        "created_at",
        server_default=None,
        existing_type=sa.DateTime(),
    )
