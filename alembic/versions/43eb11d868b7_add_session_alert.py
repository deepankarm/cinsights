"""add session_alert table

Revision ID: 43eb11d868b7
Revises: 4eb7f970a23a
Create Date: 2026-04-17 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '43eb11d868b7'
down_revision: Union[str, None] = '4eb7f970a23a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'session_alert',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('tenant_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('session_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            'alert_kind',
            sa.Enum(
                'DESTRUCTIVE_RM', 'FORCE_PUSH', 'HARD_RESET',
                'CREDENTIAL_EXPOSURE', 'PIPE_TO_SHELL',
                'CHMOD_WORLD_WRITABLE', 'SQL_DROP',
                name='alertkind',
            ),
            nullable=False,
        ),
        sa.Column('evidence', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('span_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['coding_session.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('session_alert', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_session_alert_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_session_alert_session_id'), ['session_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('session_alert', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_session_alert_session_id'))
        batch_op.drop_index(batch_op.f('ix_session_alert_tenant_id'))
    op.drop_table('session_alert')
