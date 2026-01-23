"""add testimonials table

Revision ID: 20251211_add_testimonials
Revises: 20251209_ticket_vec
Create Date: 2025-12-11
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251211_add_testimonials"
down_revision = "20251209_ticket_vec"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inboxiq_testimonials",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("consent_public", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="in_app"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_inboxiq_testimonials_account", "inboxiq_testimonials", ["account_id"])
    op.create_index("ix_inboxiq_testimonials_user", "inboxiq_testimonials", ["user_id"])


def downgrade():
    op.drop_index("ix_inboxiq_testimonials_user", table_name="inboxiq_testimonials")
    op.drop_index("ix_inboxiq_testimonials_account", table_name="inboxiq_testimonials")
    op.drop_table("inboxiq_testimonials")
