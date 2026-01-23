"""Add owner, team, assigned_to to inboxiq_tickets.

Revision ID: 20251213_ticket_assign
Revises: 20251213_add_ticket_summary_last_q
Create Date: 2025-12-13
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251213_ticket_assign"
down_revision = "20251213_add_ticket_summary_last_q"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("inboxiq_tickets", sa.Column("owner", sa.String(length=128), nullable=True))
    op.add_column("inboxiq_tickets", sa.Column("team", sa.String(length=128), nullable=True))
    op.add_column("inboxiq_tickets", sa.Column("assigned_to", sa.String(length=128), nullable=True))


def downgrade():
    op.drop_column("inboxiq_tickets", "assigned_to")
    op.drop_column("inboxiq_tickets", "team")
    op.drop_column("inboxiq_tickets", "owner")

