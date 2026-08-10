"""Create cluster_runs and fill missing clusters/cluster_members columns

Found via a real `alembic upgrade head` run against a genuinely fresh
database (twice -- the first version of this migration was itself wrong,
see below). The actual gap, precisely:

- `cluster_runs` is never created by ANY migration in the whole chain, not
  even f0eacef576cd (the initial one) -- despite dae2d3caded1 later
  ALTERing it and app/models/schema.py's Cluster.run_id having a real FK
  to it. It (and clusters/cluster_members) were evidently created via
  Base.metadata.create_all() at some point in this project's earlier POC
  history and never fully captured in a migration.
- `clusters` DOES already exist (created in f0eacef576cd -- my first
  attempt at this migration wrongly assumed it didn't and tried to
  CREATE TABLE clusters again, which fails with DuplicateTable). But its
  original definition is missing `run_id` (the FK dae2d3caded1's own
  ALTERs implicitly assume already exists) and `coherence_score`, both
  present on the current ORM model.
- `cluster_members` also already exists (f0eacef576cd), but is missing
  `membership_probability`, `outlier_score`, `is_representative` -- all
  present on the current ORM model, never added by any migration.

Inserted BEFORE dae2d3caded1 in the chain (its down_revision now points
here instead of 305857878a78) rather than appended at the tail, since a
fresh database hits dae2d3caded1 long before it would ever reach a
tail-end fix-up migration. No already-migrated database is affected by
this reordering -- the only Postgres instance that has ever gone past
dae2d3caded1 got there via `alembic stamp head` after a manual
Base.metadata.create_all(), not by actually running this or any later
migration, so it never needs to re-run this file's statements (its tables
already have this exact structure).

Revision ID: ce2fb62951bc
Revises: 305857878a78
Create Date: 2026-08-10 23:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ce2fb62951bc'
down_revision: Union[str, Sequence[str], None] = '305857878a78'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('cluster_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_name', sa.String(length=255), nullable=True),
    sa.Column('embedding_model', sa.String(length=255), nullable=True),
    sa.Column('hdbscan_version', sa.String(length=50), nullable=True),
    sa.Column('min_cluster_size', sa.Integer(), nullable=True),
    sa.Column('min_samples', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cluster_runs_id'), 'cluster_runs', ['id'], unique=False)
    op.create_index(op.f('ix_cluster_runs_run_name'), 'cluster_runs', ['run_name'], unique=True)

    # clusters already exists (f0eacef576cd) -- add the columns it's missing.
    # Safe as NOT NULL: this runs early in a fresh chain, before any
    # application code could have inserted rows.
    op.add_column('clusters', sa.Column('run_id', sa.Integer(), nullable=False))
    op.add_column('clusters', sa.Column('coherence_score', sa.Float(), nullable=True))
    op.create_foreign_key('fk_clusters_run_id_cluster_runs', 'clusters', 'cluster_runs', ['run_id'], ['id'])
    op.create_index(op.f('ix_clusters_run_id'), 'clusters', ['run_id'], unique=False)

    # cluster_members already exists (f0eacef576cd) -- add its missing columns too.
    op.add_column('cluster_members', sa.Column('membership_probability', sa.Float(), nullable=True))
    op.add_column('cluster_members', sa.Column('outlier_score', sa.Float(), nullable=True))
    op.add_column('cluster_members', sa.Column('is_representative', sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('cluster_members', 'is_representative')
    op.drop_column('cluster_members', 'outlier_score')
    op.drop_column('cluster_members', 'membership_probability')

    op.drop_index(op.f('ix_clusters_run_id'), table_name='clusters')
    op.drop_constraint('fk_clusters_run_id_cluster_runs', 'clusters', type_='foreignkey')
    op.drop_column('clusters', 'coherence_score')
    op.drop_column('clusters', 'run_id')

    op.drop_index(op.f('ix_cluster_runs_run_name'), table_name='cluster_runs')
    op.drop_index(op.f('ix_cluster_runs_id'), table_name='cluster_runs')
    op.drop_table('cluster_runs')
