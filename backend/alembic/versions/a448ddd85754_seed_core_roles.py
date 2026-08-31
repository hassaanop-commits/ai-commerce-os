"""seed core roles

Revision ID: a448ddd85754
Revises: 9d7b963b4b0b
Create Date: 2026-08-15 01:58:50.248735

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a448ddd85754'
down_revision: Union[str, Sequence[str], None] = '9d7b963b4b0b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

roles_table = sa.table(
    "roles",
    sa.column("key", sa.String),
    sa.column("name", sa.String),
    sa.column("rank", sa.SmallInteger),
)


def upgrade() -> None:
    op.bulk_insert(
        roles_table,
        [
            {"key": "owner", "name": "Owner", "rank": 1},
            {"key": "admin", "name": "Admin", "rank": 2},
            {"key": "member", "name": "Member", "rank": 3},
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM roles WHERE key IN ('owner', 'admin', 'member')")
