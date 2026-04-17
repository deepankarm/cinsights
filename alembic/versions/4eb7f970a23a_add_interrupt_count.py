"""add interrupt_count to coding_session

Revision ID: 4eb7f970a23a
Revises: 32f1f17005de
Create Date: 2026-04-16 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4eb7f970a23a'
down_revision: Union[str, None] = '32f1f17005de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('coding_session', schema=None) as batch_op:
        batch_op.add_column(sa.Column('interrupt_count', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('coding_session', schema=None) as batch_op:
        batch_op.drop_column('interrupt_count')
