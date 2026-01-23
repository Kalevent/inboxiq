"""Switch InboxIQ account reference to account_id FK."""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251208_inboxiq_account_fk"
down_revision = "20251207_inboxiq_tables"
branch_labels = None
depends_on = None


def upgrade():
    # inbox_connections: add account_id FK, drop account_uid
    op.add_column("inbox_connections", sa.Column("account_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_inbox_connections_account",
        "inbox_connections",
        "accounts",
        ["account_id"],
        ["id"],
    )
    op.drop_column("inbox_connections", "account_uid")

    # inboxiq_tickets: add account_id FK, drop account_uid
    op.add_column("inboxiq_tickets", sa.Column("account_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_inboxiq_tickets_account",
        "inboxiq_tickets",
        "accounts",
        ["account_id"],
        ["id"],
    )
    op.drop_column("inboxiq_tickets", "account_uid")


def downgrade():
    # inboxiq_tickets: restore account_uid, drop account_id
    op.add_column("inboxiq_tickets", sa.Column("account_uid", sa.VARCHAR(), nullable=True))
    op.drop_constraint("fk_inboxiq_tickets_account", "inboxiq_tickets", type_="foreignkey")
    op.drop_column("inboxiq_tickets", "account_id")

    # inbox_connections: restore account_uid, drop account_id
    op.add_column("inbox_connections", sa.Column("account_uid", sa.VARCHAR(), nullable=True))
    op.drop_constraint("fk_inbox_connections_account", "inbox_connections", type_="foreignkey")
    op.drop_column("inbox_connections", "account_id")
