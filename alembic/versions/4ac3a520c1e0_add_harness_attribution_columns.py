"""add harness attribution columns

Revision ID: 4ac3a520c1e0
Revises: 43eb11d868b7
Create Date: 2026-04-17 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '4ac3a520c1e0'
down_revision: Union[str, None] = '43eb11d868b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('coding_session', schema=None) as batch_op:
        batch_op.add_column(sa.Column('agent_version', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('effort_level', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column('adaptive_thinking_disabled', sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('coding_session', schema=None) as batch_op:
        batch_op.drop_column('adaptive_thinking_disabled')
        batch_op.drop_column('effort_level')
        batch_op.drop_column('agent_version')
