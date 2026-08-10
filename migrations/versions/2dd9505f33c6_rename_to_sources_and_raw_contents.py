"""Rename to sources and raw_contents

Revision ID: 2dd9505f33c6
Revises: cef400af3eee
Create Date: 2026-08-10 15:39:12.956655

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2dd9505f33c6'
down_revision: Union[str, Sequence[str], None] = 'cef400af3eee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.rename_table('instagram_pages', 'sources')
    op.alter_column('sources', 'username', new_column_name='external_id')
    op.alter_column('sources', 'profile_url', new_column_name='url')
    op.alter_column('sources', 'active', new_column_name='enabled')
    
    op.add_column('sources', sa.Column('platform', sa.String(50), server_default='instagram'))
    op.add_column('sources', sa.Column('source_type', sa.String(50)))
    op.add_column('sources', sa.Column('status', sa.String(50), server_default='ACTIVE'))
    
    op.rename_table('instagram_posts', 'raw_contents')
    op.alter_column('raw_contents', 'instagram_post_id', new_column_name='external_content_id')
    op.alter_column('raw_contents', 'page_id', new_column_name='source_id')
    op.alter_column('raw_contents', 'caption', new_column_name='text')
    op.alter_column('raw_contents', 'post_url', new_column_name='url')
    
    op.add_column('raw_contents', sa.Column('platform', sa.String(50), server_default='instagram'))
    op.add_column('raw_contents', sa.Column('vertical', sa.String(50), server_default='GENERAL'))
    op.add_column('raw_contents', sa.Column('content_type', sa.String(50)))
    op.add_column('raw_contents', sa.Column('title', sa.String(512)))
    op.add_column('raw_contents', sa.Column('raw_payload', sa.JSON()))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('raw_contents', 'raw_payload')
    op.drop_column('raw_contents', 'title')
    op.drop_column('raw_contents', 'content_type')
    op.drop_column('raw_contents', 'vertical')
    op.drop_column('raw_contents', 'platform')
    
    op.alter_column('raw_contents', 'url', new_column_name='post_url')
    op.alter_column('raw_contents', 'text', new_column_name='caption')
    op.alter_column('raw_contents', 'source_id', new_column_name='page_id')
    op.alter_column('raw_contents', 'external_content_id', new_column_name='instagram_post_id')
    op.rename_table('raw_contents', 'instagram_posts')
    
    op.drop_column('sources', 'status')
    op.drop_column('sources', 'source_type')
    op.drop_column('sources', 'platform')
    
    op.alter_column('sources', 'enabled', new_column_name='active')
    op.alter_column('sources', 'url', new_column_name='profile_url')
    op.alter_column('sources', 'external_id', new_column_name='username')
    op.rename_table('sources', 'instagram_pages')
