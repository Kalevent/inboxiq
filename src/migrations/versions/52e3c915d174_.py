"""empty message

Revision ID: 52e3c915d174
Revises: 4ef70f58de4c
Create Date: 2025-12-20 17:28:58.697308

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '52e3c915d174'
down_revision = '4ef70f58de4c'
branch_labels = None
depends_on = None


def upgrade():
    # Add with server defaults to backfill existing rows, then drop defaults if desired.
    with op.batch_alter_table('inboxiq_feedback', schema=None) as batch_op:
        batch_op.add_column(sa.Column('action_required', sa.String(length=16), server_default='optional', nullable=False))
        batch_op.add_column(sa.Column('metadata_json', sa.JSON(), server_default=sa.text("'{}'::jsonb"), nullable=False))
        batch_op.add_column(sa.Column('ai_decision_json', sa.JSON(), server_default=sa.text("'{}'::jsonb"), nullable=False))
        batch_op.add_column(sa.Column('ticket_id', sa.String(length=64), nullable=True))
        batch_op.create_foreign_key('fk_inboxiq_feedback_ticket', 'inboxiq_tickets', ['ticket_id'], ['id'])

    # Drop server defaults to match app model (optional).
    with op.batch_alter_table('inboxiq_feedback', schema=None) as batch_op:
        batch_op.alter_column('action_required', server_default=None)
        batch_op.alter_column('metadata_json', server_default=None)
        batch_op.alter_column('ai_decision_json', server_default=None)


def downgrade():
    with op.batch_alter_table('inboxiq_feedback', schema=None) as batch_op:
        batch_op.drop_constraint('fk_inboxiq_feedback_ticket', type_='foreignkey')
        batch_op.drop_column('ticket_id')
        batch_op.drop_column('ai_decision_json')
        batch_op.drop_column('metadata_json')
        batch_op.drop_column('action_required')
