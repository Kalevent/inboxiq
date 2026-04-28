"""Add LinkedInProspect, ICPConfig, Lead.linkedin_url

Revision ID: de741d7100b5
Revises: 0352216673b7
Create Date: 2026-04-27 22:34:04.807827

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'de741d7100b5'
down_revision = '0352216673b7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'linkedin_prospects',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('lead_id', sa.String(length=64), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('company_name', sa.String(length=255), nullable=True),
        sa.Column('job_title', sa.String(length=255), nullable=True),
        sa.Column('industry', sa.String(length=100), nullable=True),
        sa.Column('linkedin_url', sa.String(length=500), nullable=False),
        sa.Column('source', sa.String(length=20), server_default='auto', nullable=False),
        sa.Column('status',
            sa.Enum(
                'pending', 'connection_sent', 'connected',
                'message_2_sent', 'message_3_sent',
                'replied', 'qualified', 'disqualified',
                name='linkedin_prospect_status_enum',
            ),
            server_default='pending', nullable=False,
        ),
        sa.Column('fit_score', sa.Integer(), nullable=True),
        sa.Column('connection_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('connected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('message_2_due_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('message_2_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('message_3_due_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('message_3_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('msg_1_draft', sa.Text(), nullable=True),
        sa.Column('msg_2_draft', sa.Text(), nullable=True),
        sa.Column('msg_3_draft', sa.Text(), nullable=True),
        sa.Column('suggested_post_id', sa.String(length=64), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id']),
        sa.ForeignKeyConstraint(['suggested_post_id'], ['blog_posts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_id', 'linkedin_url', name='uq_li_prospect_account_url'),
    )
    op.create_index('idx_li_prospect_account_status', 'linkedin_prospects', ['account_id', 'status'])
    op.create_index('idx_li_prospect_due', 'linkedin_prospects', ['message_2_due_at', 'message_3_due_at'])

    op.create_table(
        'icp_configs',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('titles', sa.JSON(), nullable=False),
        sa.Column('industries', sa.JSON(), nullable=False),
        sa.Column('company_size_min', sa.Integer(), nullable=False),
        sa.Column('company_size_max', sa.Integer(), nullable=False),
        sa.Column('geographies', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_id'),
    )

    with op.batch_alter_table('automation_studio_waitlist', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_automation_studio_waitlist_email'))
        batch_op.create_index(batch_op.f('ix_automation_studio_waitlist_email'), ['email'], unique=True)

    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.add_column(sa.Column('linkedin_url', sa.String(length=500), nullable=True))
        batch_op.create_index(batch_op.f('ix_leads_linkedin_url'), ['linkedin_url'], unique=False)


def downgrade():
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_leads_linkedin_url'))
        batch_op.drop_column('linkedin_url')

    with op.batch_alter_table('automation_studio_waitlist', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_automation_studio_waitlist_email'))
        batch_op.create_index(batch_op.f('ix_automation_studio_waitlist_email'), ['email'], unique=False)

    op.drop_table('icp_configs')
    op.drop_index('idx_li_prospect_due', table_name='linkedin_prospects')
    op.drop_index('idx_li_prospect_account_status', table_name='linkedin_prospects')
    op.drop_table('linkedin_prospects')
    sa.Enum(name='linkedin_prospect_status_enum').drop(op.get_bind())
