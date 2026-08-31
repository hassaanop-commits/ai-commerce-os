"""add updated_at trigger

Revision ID: 6d850b6518c5
Revises: ed0839c50901
Create Date: 2026-08-15 00:59:23.178655

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '6d850b6518c5'
down_revision: Union[str, Sequence[str], None] = 'ed0839c50901'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Every table with an updated_at column (TimestampMixin), i.e. every table
# except the append-only/no-update lookup and log tables: roles, marketplaces
# (system lookups, effectively static) and ai_runs (write-once event record).
TABLES_WITH_UPDATED_AT = (
    "users",
    "organizations",
    "organization_members",
    "products",
    "product_assets",
    "marketplace_connections",
    "listings",
    "usage_tracking",
    "plans",
    "subscriptions",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION set_updated_at() RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in TABLES_WITH_UPDATED_AT:
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_set_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION set_updated_at();
            """
        )


def downgrade() -> None:
    for table in TABLES_WITH_UPDATED_AT:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_set_updated_at ON {table};")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at();")
