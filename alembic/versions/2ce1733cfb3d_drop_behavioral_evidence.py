"""drop behavioral_evidence table

Revision ID: 2ce1733cfb3d
Revises: c028244000ef
Create Date: 2026-04-17 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = '2ce1733cfb3d'
down_revision: Union[str, None] = 'c028244000ef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('behavioral_evidence')


def downgrade() -> None:
    pass
