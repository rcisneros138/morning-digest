"""add refresh tokens

Revision ID: d4a1b2c3e4f5
Revises: c3fc8f048e8b
Create Date: 2026-02-07 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4a1b2c3e4f5'
down_revision: Union[str, Sequence[str], None] = 'c3fc8f048e8b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('refresh_tokens',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.Text(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('revoked_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_refresh_tokens_token_hash', 'refresh_tokens', ['token_hash'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_refresh_tokens_token_hash', table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
