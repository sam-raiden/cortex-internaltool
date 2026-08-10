"""Widen sources.last_post_id to fit real-world URLs (same root cause as
cc000518ae0a -- found immediately after applying that one, in the same live
RSS collection run: RSS last_post_id is often a full entry URL, not a short id)

Revision ID: 4ddb52c6f426
Revises: cc000518ae0a
Create Date: 2026-08-10 22:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4ddb52c6f426'
down_revision: Union[str, Sequence[str], None] = 'cc000518ae0a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('sources', 'last_post_id',
                     existing_type=sa.String(length=100),
                     type_=sa.String(length=512),
                     existing_nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('sources', 'last_post_id',
                     existing_type=sa.String(length=512),
                     type_=sa.String(length=100),
                     existing_nullable=True)
