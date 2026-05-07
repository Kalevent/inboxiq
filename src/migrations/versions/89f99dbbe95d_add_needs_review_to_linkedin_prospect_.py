"""add needs_review to linkedin_prospect_status_enum

Revision ID: 89f99dbbe95d
Revises: b6570669bcb2
Create Date: 2026-05-07 19:53:33.045504

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '89f99dbbe95d'
down_revision = 'b6570669bcb2'
branch_labels = None
depends_on = None


def upgrade():
    # Alembic autogenerate cannot detect new values added to an existing
    # Postgres ENUM, so the ADD VALUE is written by hand. IF NOT EXISTS keeps
    # the upgrade idempotent (safe to re-run after a downgrade locally).
    op.execute(
        "ALTER TYPE linkedin_prospect_status_enum ADD VALUE IF NOT EXISTS 'needs_review'"
    )

    # Unrelated index drift picked up by autogenerate on the same run.
    with op.batch_alter_table('automation_studio_waitlist', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_automation_studio_waitlist_email'))
        batch_op.create_index('ix_automation_studio_waitlist_email', ['email'], unique=False)


def downgrade():
    # Postgres has no DROP VALUE for enums; the 'needs_review' value cannot be
    # removed by a downgrade. Reverse only the index drift.
    with op.batch_alter_table('automation_studio_waitlist', schema=None) as batch_op:
        batch_op.drop_index('ix_automation_studio_waitlist_email')
        batch_op.create_index(batch_op.f('ix_automation_studio_waitlist_email'), ['email'], unique=True)
