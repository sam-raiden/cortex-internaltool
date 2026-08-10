"""Widen raw_contents.external_content_id to fit real-world URLs

Found via a live RSS collection run: real news-site URLs (long SEO slugs)
routinely exceed 100 chars, used as external_content_id when a feed entry
has no id/guid. Widened to match RawContent.url's existing 512-char limit.

Revision ID: cc000518ae0a
Revises: 1b813a1bfd07
Create Date: 2026-08-10 22:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cc000518ae0a'
down_revision: Union[str, Sequence[str], None] = '1b813a1bfd07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('raw_contents', 'external_content_id',
                     existing_type=sa.String(length=100),
                     type_=sa.String(length=512),
                     existing_nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('raw_contents', 'external_content_id',
                     existing_type=sa.String(length=512),
                     type_=sa.String(length=100),
                     existing_nullable=False)
