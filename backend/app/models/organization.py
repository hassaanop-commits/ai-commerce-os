from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.ai_run import AIRun
    from app.models.audit_log import AuditLog
    from app.models.listing import Listing
    from app.models.marketplace_connection import MarketplaceConnection
    from app.models.organization_member import OrganizationMember
    from app.models.product import Product
    from app.models.product_asset import ProductAsset
    from app.models.subscription import Subscription
    from app.models.usage_tracking import UsageTracking
    from app.models.user import User


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'suspended', 'deleted')", name="ck_organizations_status"),
        Index(
            "ix_organizations_status_live",
            "status",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped["User | None"] = relationship(
        back_populates="created_organizations", foreign_keys=[created_by_user_id]
    )
    members: Mapped[list["OrganizationMember"]] = relationship(back_populates="organization")
    products: Mapped[list["Product"]] = relationship(back_populates="organization")
    product_assets: Mapped[list["ProductAsset"]] = relationship(back_populates="organization")
    marketplace_connections: Mapped[list["MarketplaceConnection"]] = relationship(back_populates="organization")
    listings: Mapped[list["Listing"]] = relationship(back_populates="organization")
    ai_runs: Mapped[list["AIRun"]] = relationship(back_populates="organization")
    usage_records: Mapped[list["UsageTracking"]] = relationship(back_populates="organization")
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="organization")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="organization")
