"""Merge heads for billing and inboxiq branches."""

from alembic import op
import sqlalchemy as sa  # noqa: F401

# revision identifiers, used by Alembic.
revision = "20251212_merge_heads"
down_revision = ("5fcb177ae0df", "20251212_add_testimonial_status")
branch_labels = None
depends_on = None


def upgrade():
    # No-op merge migration.
    pass


def downgrade():
    # No-op downgrade for merge point.
    pass
