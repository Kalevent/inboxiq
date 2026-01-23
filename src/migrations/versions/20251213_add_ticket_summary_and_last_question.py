"""Add summary and last_question to inboxiq_tickets.

Revision ID: 20251213_add_ticket_summary_last_q
Revises: 20251213_add_due_at
Create Date: 2025-12-13
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251213_add_ticket_summary_last_q"
down_revision = "20251213_add_due_at"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("inboxiq_tickets", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column("inboxiq_tickets", sa.Column("last_question", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("inboxiq_tickets", "last_question")
    op.drop_column("inboxiq_tickets", "summary")

