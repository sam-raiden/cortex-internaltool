"""stage 12 source governance fields

Revision ID: 226a05bf904b
Revises: 2dd9505f33c6
Create Date: 2026-08-10 16:04:42.420763

Adds source governance columns (name, health, configuration) to `sources`.

Also finishes the sources/raw_contents rename started in 2dd9505f33c6:
`collection_errors.page_id` and `collection_page_results.page_id` were left
behind as stale column/index/constraint names even though the ORM model
(schema.py) already reads/writes them as `source_id`. Renamed here for
consistency; existing rows are preserved (rename, not add+drop).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '226a05bf904b'
down_revision: Union[str, Sequence[str], None] = '2dd9505f33c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- Stage 12: source governance fields ---
    op.add_column('sources', sa.Column('name', sa.String(length=255), nullable=True))
    op.add_column('sources', sa.Column('health', sa.String(length=50), nullable=False, server_default='UNKNOWN'))
    op.add_column('sources', sa.Column('configuration', sa.JSON(), nullable=True))

    # --- finish sources/raw_contents rename drift left by 2dd9505f33c6 ---
    op.drop_constraint(op.f('collection_errors_page_id_fkey'), 'collection_errors', type_='foreignkey')
    op.alter_column('collection_errors', 'page_id', new_column_name='source_id')
    op.create_foreign_key(None, 'collection_errors', 'sources', ['source_id'], ['id'])

    op.drop_index(op.f('ix_collection_page_results_page_id'), table_name='collection_page_results')
    op.drop_constraint(op.f('collection_page_results_page_id_fkey'), 'collection_page_results', type_='foreignkey')
    op.alter_column('collection_page_results', 'page_id', new_column_name='source_id')
    op.create_index(op.f('ix_collection_page_results_source_id'), 'collection_page_results', ['source_id'], unique=False)
    op.create_foreign_key(None, 'collection_page_results', 'sources', ['source_id'], ['id'])

    # stale index names from the instagram_pages/instagram_posts era
    op.drop_index(op.f('ix_instagram_posts_id'), table_name='raw_contents')
    op.drop_index(op.f('ix_instagram_posts_instagram_post_id'), table_name='raw_contents')
    op.drop_index(op.f('ix_instagram_posts_page_id'), table_name='raw_contents')
    op.drop_index(op.f('ix_instagram_posts_published_at'), table_name='raw_contents')
    op.create_index(op.f('ix_raw_contents_external_content_id'), 'raw_contents', ['external_content_id'], unique=True)
    op.create_index(op.f('ix_raw_contents_id'), 'raw_contents', ['id'], unique=False)
    op.create_index(op.f('ix_raw_contents_published_at'), 'raw_contents', ['published_at'], unique=False)
    op.create_index(op.f('ix_raw_contents_source_id'), 'raw_contents', ['source_id'], unique=False)

    op.drop_index(op.f('ix_instagram_pages_active'), table_name='sources')
    op.drop_index(op.f('ix_instagram_pages_id'), table_name='sources')
    op.drop_index(op.f('ix_instagram_pages_username'), table_name='sources')
    op.drop_index(op.f('ix_instagram_pages_vertical'), table_name='sources')
    op.create_index(op.f('ix_sources_enabled'), 'sources', ['enabled'], unique=False)
    op.create_index(op.f('ix_sources_external_id'), 'sources', ['external_id'], unique=True)
    op.create_index(op.f('ix_sources_id'), 'sources', ['id'], unique=False)
    op.create_index(op.f('ix_sources_platform'), 'sources', ['platform'], unique=False)
    op.create_index(op.f('ix_sources_vertical'), 'sources', ['vertical'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_sources_vertical'), table_name='sources')
    op.drop_index(op.f('ix_sources_platform'), table_name='sources')
    op.drop_index(op.f('ix_sources_id'), table_name='sources')
    op.drop_index(op.f('ix_sources_external_id'), table_name='sources')
    op.drop_index(op.f('ix_sources_enabled'), table_name='sources')
    op.create_index(op.f('ix_instagram_pages_vertical'), 'sources', ['vertical'], unique=False)
    op.create_index(op.f('ix_instagram_pages_username'), 'sources', ['external_id'], unique=True)
    op.create_index(op.f('ix_instagram_pages_id'), 'sources', ['id'], unique=False)
    op.create_index(op.f('ix_instagram_pages_active'), 'sources', ['enabled'], unique=False)

    op.drop_index(op.f('ix_raw_contents_source_id'), table_name='raw_contents')
    op.drop_index(op.f('ix_raw_contents_published_at'), table_name='raw_contents')
    op.drop_index(op.f('ix_raw_contents_id'), table_name='raw_contents')
    op.drop_index(op.f('ix_raw_contents_external_content_id'), table_name='raw_contents')
    op.create_index(op.f('ix_instagram_posts_published_at'), 'raw_contents', ['published_at'], unique=False)
    op.create_index(op.f('ix_instagram_posts_page_id'), 'raw_contents', ['source_id'], unique=False)
    op.create_index(op.f('ix_instagram_posts_instagram_post_id'), 'raw_contents', ['external_content_id'], unique=True)
    op.create_index(op.f('ix_instagram_posts_id'), 'raw_contents', ['id'], unique=False)

    op.drop_constraint(None, 'collection_page_results', type_='foreignkey')
    op.drop_index(op.f('ix_collection_page_results_source_id'), table_name='collection_page_results')
    op.alter_column('collection_page_results', 'source_id', new_column_name='page_id')
    op.create_index(op.f('ix_collection_page_results_page_id'), 'collection_page_results', ['page_id'], unique=False)
    op.create_foreign_key(op.f('collection_page_results_page_id_fkey'), 'collection_page_results', 'sources', ['page_id'], ['id'])

    op.drop_constraint(None, 'collection_errors', type_='foreignkey')
    op.alter_column('collection_errors', 'source_id', new_column_name='page_id')
    op.create_foreign_key(op.f('collection_errors_page_id_fkey'), 'collection_errors', 'sources', ['page_id'], ['id'])

    op.drop_column('sources', 'configuration')
    op.drop_column('sources', 'health')
    op.drop_column('sources', 'name')
