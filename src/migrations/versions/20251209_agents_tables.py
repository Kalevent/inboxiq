"""Add ai_agents and mcp_server_catalog tables for InboxIQ."""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251209_agents_tables"
down_revision = "20251208_inboxiq_account_fk"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_agents",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("mcp_servers", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("capabilities", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("triggers", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("human_review", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("graph_node_ref", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "mcp_server_catalog",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("command", sa.JSON(), nullable=False),
        sa.Column("env", sa.JSON(), nullable=True),
        sa.Column("cwd", sa.String(length=512), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("label"),
    )


def downgrade():
    op.drop_table("mcp_server_catalog")
    op.drop_table("ai_agents")
