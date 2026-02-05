"""add digest pipeline tables

Revision ID: c3fc8f048e8b
Revises: 26ffec7ad5db
Create Date: 2026-02-04 15:42:22.467810

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3fc8f048e8b'
down_revision: Union[str, Sequence[str], None] = '26ffec7ad5db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('digests',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('tier_at_creation', sa.Enum('free', 'paid', name='usertier', create_type=False), nullable=False),
    sa.Column('generated_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'date', name='uq_digest_user_date')
    )
    op.create_table('digest_groups',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('digest_id', sa.UUID(), nullable=False),
    sa.Column('topic_label', sa.Text(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['digest_id'], ['digests.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('digest_items',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('group_id', sa.UUID(), nullable=False),
    sa.Column('article_id', sa.UUID(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('ai_summary', sa.Text(), nullable=True),
    sa.Column('is_primary', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['article_id'], ['articles.id'], ),
    sa.ForeignKeyConstraint(['group_id'], ['digest_groups.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('user_interactions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('article_id', sa.UUID(), nullable=False),
    sa.Column('type', sa.Enum('read', 'tapped_through', 'saved', 'dismissed', name='interactiontype'), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['article_id'], ['articles.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_user_interactions_user_type', 'user_interactions', ['user_id', 'type'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_user_interactions_user_type', table_name='user_interactions')
    op.drop_table('user_interactions')
    op.drop_table('digest_items')
    op.drop_table('digest_groups')
    op.drop_table('digests')
