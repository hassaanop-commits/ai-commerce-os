"""add product_assets.approval_status

Revision ID: 79037475aab3
Revises: a448ddd85754
Create Date: 2026-08-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '79037475aab3'
down_revision: Union[str, Sequence[str], None] = 'a448ddd85754'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'product_assets',
        sa.Column('approval_status', sa.String(length=20), server_default='not_required', nullable=False),
    )
    op.create_check_constraint(
        'ck_product_assets_approval_status',
        'product_assets',
        "approval_status IN ('not_required', 'pending_review', 'approved', 'rejected')",
    )
    op.create_check_constraint(
        'ck_product_assets_primary_requires_approval',
        'product_assets',
        "NOT is_primary OR approval_status IN ('approved', 'not_required')",
    )
    op.create_index(
        'ix_product_assets_org_approval_status',
        'product_assets',
        ['organization_id', 'approval_status'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_product_assets_org_approval_status', table_name='product_assets')
    op.drop_constraint('ck_product_assets_primary_requires_approval', 'product_assets', type_='check')
    op.drop_constraint('ck_product_assets_approval_status', 'product_assets', type_='check')
    op.drop_column('product_assets', 'approval_status')
