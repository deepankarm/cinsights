"""add behavioral_evidence table

Revision ID: b4dddbe208e2
Revises: 4ac3a520c1e0
Create Date: 2026-04-17 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'b4dddbe208e2'
down_revision: Union[str, None] = '4ac3a520c1e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'behavioral_evidence',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('tenant_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('session_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            'category',
            sa.Enum(
                'OWNERSHIP_DODGE', 'REASONING_LOOP', 'PERMISSION_SEEKING',
                'PREMATURE_STOP', 'SIMPLEST_MENTALITY', 'SELF_ADMITTED_ERROR',
                name='behaviorcategory',
            ),
            nullable=False,
        ),
        sa.Column('turn_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('quote', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('explanation', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            'confidence',
            sa.Enum('HIGH', 'MEDIUM', 'LOW', name='behaviorconfidence'),
            nullable=False,
        ),
        sa.Column('validated', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['coding_session.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('behavioral_evidence', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_behavioral_evidence_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_behavioral_evidence_session_id'), ['session_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('behavioral_evidence', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_behavioral_evidence_session_id'))
        batch_op.drop_index(batch_op.f('ix_behavioral_evidence_tenant_id'))
    op.drop_table('behavioral_evidence')
