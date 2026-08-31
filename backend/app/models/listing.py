from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CHAR, CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.marketplace_connection import MarketplaceConnection
    from app.models.organization import Organization
    from app.models.product import Product


class Listing(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "listings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'approved', 'publishing', 'active', 'error', 'ended')",
            name="ck_listings_status",
        ),
        Index("ix_listings_product_id", "product_id"),
        Index("ix_listings_org_status", "organization_id", "status"),
        Index("ix_listings_connection_status", "marketplace_connection_id", "status"),
        Index(
            "uq_listings_live_product_per_connection",
            "marketplace_connection_id",
            "product_id",
            unique=True,
            postgresql_where=text("status <> 'ended'"),
        ),
        Index(
            "uq_listings_external_id_per_connection",
            "marketplace_connection_id",
            "external_listing_id",
            unique=True,
            postgresql_where=text("external_listing_id IS NOT NULL"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    marketplace_connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplace_connections.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default="USD")
    listing_data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    external_listing_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    marketplace_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    organization: Mapped["Organization"] = relationship(back_populates="listings")
    product: Mapped["Product"] = relationship(back_populates="listings")
    marketplace_connection: Mapped["MarketplaceConnection"] = relationship(back_populates="listings")
