"""Add trend_semantic_analyses table (Stage 21 LLM semantic layer)

Revision ID: 1b813a1bfd07
Revises: 226a05bf904b
Create Date: 2026-08-10 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b813a1bfd07'
down_revision: Union[str, Sequence[str], None] = '226a05bf904b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('trend_semantic_analyses',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('trend_id', sa.Integer(), nullable=False),
    sa.Column('evidence_hash', sa.String(length=64), nullable=False),
    sa.Column('llm_model', sa.String(length=100), nullable=False),
    sa.Column('llm_prompt_version', sa.String(length=50), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('normalized_topic', sa.String(length=255), nullable=True),
    sa.Column('title', sa.String(length=255), nullable=True),
    sa.Column('english_title', sa.String(length=255), nullable=True),
    sa.Column('tamil_title', sa.String(length=255), nullable=True),
    sa.Column('category', sa.String(length=50), nullable=True),
    sa.Column('hashtags', sa.JSON(), nullable=True),
    sa.Column('micro_insight', sa.Text(), nullable=True),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('explanation', sa.Text(), nullable=True),
    sa.Column('confidence_reason', sa.Text(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('raw_response', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['trend_id'], ['trends.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_trend_semantic_analyses_id'), 'trend_semantic_analyses', ['id'], unique=False)
    op.create_index(op.f('ix_trend_semantic_analyses_trend_id'), 'trend_semantic_analyses', ['trend_id'], unique=False)
    op.create_index(op.f('ix_trend_semantic_analyses_evidence_hash'), 'trend_semantic_analyses', ['evidence_hash'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_trend_semantic_analyses_evidence_hash'), table_name='trend_semantic_analyses')
    op.drop_index(op.f('ix_trend_semantic_analyses_trend_id'), table_name='trend_semantic_analyses')
    op.drop_index(op.f('ix_trend_semantic_analyses_id'), table_name='trend_semantic_analyses')
    op.drop_table('trend_semantic_analyses')
