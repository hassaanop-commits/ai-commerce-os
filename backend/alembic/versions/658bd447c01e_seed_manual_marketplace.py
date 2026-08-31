"""seed manual marketplace

Revision ID: 658bd447c01e
Revises: 79037475aab3
Create Date: 2026-08-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '658bd447c01e'
down_revision: Union[str, Sequence[str], None] = '79037475aab3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

marketplaces_table = sa.table(
    "marketplaces",
    sa.column("key", sa.String),
    sa.column("name", sa.String),
    sa.column("is_active", sa.Boolean),
)


def upgrade() -> None:
    op.bulk_insert(
        marketplaces_table,
        [
            {"key": "manual", "name": "Manual (test)", "is_active": True},
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM marketplaces WHERE key = 'manual'")
