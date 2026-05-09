"""video_renders.heygen_render_url to Text

Revision ID: ef301df23894
Revises: 89f99dbbe95d
Create Date: 2026-05-09 12:26:36.402896

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ef301df23894'
down_revision = '89f99dbbe95d'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('video_renders', schema=None) as batch_op:
        batch_op.alter_column('heygen_render_url',
               existing_type=sa.VARCHAR(length=512),
               type_=sa.Text(),
               existing_nullable=True)


def downgrade():
    with op.batch_alter_table('video_renders', schema=None) as batch_op:
        batch_op.alter_column('heygen_render_url',
               existing_type=sa.Text(),
               type_=sa.VARCHAR(length=512),
               existing_nullable=True)
