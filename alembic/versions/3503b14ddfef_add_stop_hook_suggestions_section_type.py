"""add stop_hook_suggestions to digest section types

Revision ID: 3503b14ddfef
Revises: b4dddbe208e2
Create Date: 2026-04-17 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = '3503b14ddfef'
down_revision: Union[str, None] = 'b4dddbe208e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite doesn't enforce enum constraints at the DB level when using
    # CHECK constraints from SQLModel. The new value is accepted by the
    # application layer (DigestSectionType enum). No DDL change needed
    # for SQLite; for Postgres, we'd ALTER TYPE here.
    pass


def downgrade() -> None:
    pass
