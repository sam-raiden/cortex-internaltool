"""widen raw_content url and external_content_id to 2048

Revision ID: 437fb8132f1f
Revises: 4ddb52c6f426
Create Date: 2026-08-11 09:46:32.205433

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '437fb8132f1f'
down_revision: Union[str, Sequence[str], None] = '4ddb52c6f426'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('raw_contents', 'external_content_id',
                     existing_type=sa.String(length=512),
                     type_=sa.String(length=2048),
                     existing_nullable=False)
    op.alter_column('raw_contents', 'url',
                     existing_type=sa.String(length=512),
                     type_=sa.String(length=2048),
                     existing_nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('raw_contents', 'url',
                     existing_type=sa.String(length=2048),
                     type_=sa.String(length=512),
                     existing_nullable=False)
    op.alter_column('raw_contents', 'external_content_id',
                     existing_type=sa.String(length=2048),
                     type_=sa.String(length=512),
                     existing_nullable=False)
