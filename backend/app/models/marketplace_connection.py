from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, LargeBinary, SmallInteger, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.listing import Listing
    from app.models.marketplace import Marketplace
    from app.models.organization import Organization


class MarketplaceConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "marketplace_connections"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "marketplace_id",
            "external_account_id",
            name="uq_marketplace_connections_org_marketplace_account",
        ),
        CheckConstraint(
            "status IN ('connected', 'disconnected', 'error', 'expired')",
            name="ck_marketplace_connections_status",
        ),
        Index("ix_marketplace_connections_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    marketplace_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("marketplaces.id"), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    external_account_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    credentials_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    scopes: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="disconnected")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped["Organization"] = relationship(back_populates="marketplace_connections")
    marketplace: Mapped["Marketplace"] = relationship(back_populates="connections")
    listings: Mapped[list["Listing"]] = relationship(back_populates="marketplace_connection")
