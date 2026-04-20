"""add llm_call_log table

Revision ID: 32f1f17005de
Revises: 0929390eaedb
Create Date: 2026-04-16 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '32f1f17005de'
down_revision: Union[str, None] = '0929390eaedb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'llm_call_log',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('tenant_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            'call_kind',
            sa.Enum(
                'SESSION_ANALYSIS',
                'PROJECT_DETECTION',
                'DIGEST_NARRATIVE',
                'DIGEST_ACTIONS',
                'DIGEST_FORWARD',
                name='llmcallkind',
            ),
            nullable=False,
        ),
        sa.Column(
            'scope_type',
            sa.Enum('SESSION', 'DIGEST', 'UNKNOWN', name='llmcallscopetype'),
            nullable=False,
        ),
        sa.Column('scope_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('model', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('provider', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completion_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cache_read_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cache_write_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('duration_ms', sa.Float(), nullable=True),
        sa.Column(
            'status',
            sa.Enum('SUCCESS', 'FAILURE', name='llmcallstatus'),
            nullable=False,
        ),
        sa.Column('error_message', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('dollar_cost', sa.Float(), nullable=True),
        sa.Column('schema_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('metadata_json', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('llm_call_log', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_llm_call_log_tenant_id'), ['tenant_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_llm_call_log_call_kind'), ['call_kind'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_llm_call_log_scope_id'), ['scope_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_llm_call_log_created_at'), ['created_at'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('llm_call_log', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_llm_call_log_created_at'))
        batch_op.drop_index(batch_op.f('ix_llm_call_log_scope_id'))
        batch_op.drop_index(batch_op.f('ix_llm_call_log_call_kind'))
        batch_op.drop_index(batch_op.f('ix_llm_call_log_tenant_id'))
    op.drop_table('llm_call_log')
