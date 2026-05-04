"""add icp_pain_points table

Revision ID: 5e4a74c40a9f
Revises: e892d2d3c118
Create Date: 2026-05-03 18:17:26.338433

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '5e4a74c40a9f'
down_revision = 'e892d2d3c118'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS icp_pain_points (
            id VARCHAR(64) NOT NULL,
            account_id INTEGER NOT NULL,
            icp_config_id VARCHAR(64) NOT NULL,
            pain_point TEXT NOT NULL,
            consequence TEXT NOT NULL,
            persona VARCHAR(255),
            priority INTEGER NOT NULL DEFAULT 0,
            active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            FOREIGN KEY (icp_config_id) REFERENCES icp_configs(id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_icp_pain_points_account ON icp_pain_points (account_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_icp_pain_points_priority ON icp_pain_points (account_id, priority)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_icp_pain_points_priority")
    op.execute("DROP INDEX IF EXISTS idx_icp_pain_points_account")
    op.execute("DROP TABLE IF EXISTS icp_pain_points")
