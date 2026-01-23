"""add status to testimonials

Revision ID: 20251212_add_testimonial_status
Revises: 20251211_add_testimonials
Create Date: 2025-12-12
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251212_add_testimonial_status"
down_revision = "20251211_add_testimonials"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("inboxiq_testimonials", sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"))


def downgrade():
    op.drop_column("inboxiq_testimonials", "status")
