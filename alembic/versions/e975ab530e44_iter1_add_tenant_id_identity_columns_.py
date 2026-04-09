"""iter1: add tenant_id, identity columns, refresh_run table

Revision ID: e975ab530e44
Revises: a9f423e49825
Create Date: 2026-04-09 17:58:51.710552

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'e975ab530e44'
down_revision: Union[str, None] = 'a9f423e49825'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOTE: server_default values let us add NOT NULL columns to populated tables.
    # New rows written from Python use the SQLModel field defaults; the server_default
    # is just for backfilling existing rows.
    op.create_table('refresh_run',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('tenant_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='default'),
    sa.Column('command', sa.Enum('REFRESH', 'ANALYZE', 'DIGEST', name='refreshruncommand'), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.Column('status', sa.Enum('RUNNING', 'SUCCESS', 'FAILED', name='refreshrunstatus'), nullable=False),
    sa.Column('sessions_analyzed', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('digests_generated', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('total_prompt_tokens', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('total_completion_tokens', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('db_size_bytes', sa.Integer(), nullable=True),
    sa.Column('wall_seconds', sa.Float(), nullable=True),
    sa.Column('error_message', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('metadata_json', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('refresh_run', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_refresh_run_started_at'), ['started_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_refresh_run_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('coding_session', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='default'))
        batch_op.add_column(sa.Column('source', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='phoenix'))
        batch_op.add_column(sa.Column('agent_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='claude-code'))
        batch_op.create_index(batch_op.f('ix_coding_session_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('digest', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='default'))
        batch_op.create_index(batch_op.f('ix_digest_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('digest_section', schema=None) as batch_op:
        batch_op.add_column(sa.Column('prompt_version', sqlmodel.sql.sqltypes.AutoString(), nullable=True))

    with op.batch_alter_table('insight', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='default'))
        batch_op.add_column(sa.Column('prompt_version', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.create_index(batch_op.f('ix_insight_tenant_id'), ['tenant_id'], unique=False)

    with op.batch_alter_table('tool_call', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='default'))
        batch_op.create_index(batch_op.f('ix_tool_call_tenant_id'), ['tenant_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('tool_call', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tool_call_tenant_id'))
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('insight', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_insight_tenant_id'))
        batch_op.drop_column('prompt_version')
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('digest_section', schema=None) as batch_op:
        batch_op.drop_column('prompt_version')

    with op.batch_alter_table('digest', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_digest_tenant_id'))
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('coding_session', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_coding_session_tenant_id'))
        batch_op.drop_column('agent_type')
        batch_op.drop_column('source')
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('refresh_run', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_refresh_run_tenant_id'))
        batch_op.drop_index(batch_op.f('ix_refresh_run_started_at'))

    op.drop_table('refresh_run')
