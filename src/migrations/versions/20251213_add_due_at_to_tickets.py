"""Add due_at to inboxiq_tickets for SLA tracking.

Revision ID: 20251213_add_due_at
Revises: ce126edcbd61
Create Date: 2025-12-13
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251213_add_due_at"
down_revision = "ce126edcbd61"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("inboxiq_tickets", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("inboxiq_tickets", "due_at")

