"""drop session_alert table

Revision ID: c028244000ef
Revises: 3503b14ddfef
Create Date: 2026-04-17 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'c028244000ef'
down_revision: Union[str, None] = '3503b14ddfef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('session_alert')


def downgrade() -> None:
    op.create_table(
        'session_alert',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('tenant_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('session_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('alert_kind', sa.Enum(
            'DESTRUCTIVE_RM', 'FORCE_PUSH', 'HARD_RESET',
            'CREDENTIAL_EXPOSURE', 'PIPE_TO_SHELL',
            'CHMOD_WORLD_WRITABLE', 'SQL_DROP',
            name='alertkind',
        ), nullable=False),
        sa.Column('evidence', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('span_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['coding_session.id']),
        sa.PrimaryKeyConstraint('id'),
    )
