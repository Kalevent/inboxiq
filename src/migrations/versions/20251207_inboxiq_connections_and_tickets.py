"""Add InboxIQ connections and tickets tables (new app chain).

Revision ID: 20251207_inboxiq_connections_and_tickets
Revises: 20251206_defaults_for_accounts_and_users
Create Date: 2025-12-07 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
# Keep revision length <= 32 to satisfy alembic_version column.
revision = "20251207_inboxiq_tables"
down_revision = "20251206_acct_defaults_v1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inbox_connections",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("account_uid", sa.String(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("email_address", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="connected"),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_inbox_connections_user"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_provider_inbox"),
    )

    op.create_table(
        "inboxiq_tickets",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("account_uid", sa.String(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("from_email", sa.String(length=255), nullable=False),
        sa.Column("body_preview", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=False, server_default="general"),
        sa.Column("priority", sa.String(length=8), nullable=False, server_default="P2"),
        sa.Column("sentiment", sa.String(length=32), nullable=False, server_default="neutral"),
        sa.Column("entities", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="new"),
        sa.Column("message_id", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("provider_thread_url", sa.String(length=512), nullable=True),
        sa.Column("decision", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("manual_override", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("override_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_inboxiq_tickets_user"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "provider", name="uq_ticket_message_provider"),
    )


def downgrade():
    op.drop_table("inboxiq_tickets")
    op.drop_table("inbox_connections")
