"""add dspy training metrics

Revision ID: 7c3f1b9d3a12
Revises: 4b1ff4d69fda
Create Date: 2026-01-25
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7c3f1b9d3a12"
down_revision = "4b1ff4d69fda"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dspy_training_metrics",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=True),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="openai"),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("eval_count", sa.Integer(), nullable=True),
        sa.Column("train_accuracy", sa.Float(), nullable=True),
        sa.Column("eval_accuracy", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_dspy_training_metrics_account",
        "dspy_training_metrics",
        ["account_id"],
    )


def downgrade():
    op.drop_index("ix_dspy_training_metrics_account", table_name="dspy_training_metrics")
    op.drop_table("dspy_training_metrics")
