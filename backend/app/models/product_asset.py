from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.ai_run import AIRun
    from app.models.marketplace import Marketplace
    from app.models.organization import Organization
    from app.models.product import Product


class ProductAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "product_assets"
    __table_args__ = (
        CheckConstraint("source IN ('upload', 'ai_generated', 'processed')", name="ck_product_assets_source"),
        CheckConstraint("asset_type IN ('image', 'video', 'document')", name="ck_product_assets_asset_type"),
        CheckConstraint("status IN ('pending', 'processing', 'ready', 'failed')", name="ck_product_assets_status"),
        CheckConstraint(
            "approval_status IN ('not_required', 'pending_review', 'approved', 'rejected')",
            name="ck_product_assets_approval_status",
        ),
        # Belt-and-suspenders alongside the service-layer guard in
        # app.services.product_assets: an AI-generated/processed asset that
        # hasn't been approved can never become the primary image, even if a
        # future code path forgets to check.
        CheckConstraint(
            "NOT is_primary OR approval_status IN ('approved', 'not_required')",
            name="ck_product_assets_primary_requires_approval",
        ),
        Index("ix_product_assets_product_position", "product_id", "position"),
        Index(
            "uq_product_assets_primary_per_product",
            "product_id",
            unique=True,
            postgresql_where=text("is_primary = true AND marketplace_id IS NULL"),
        ),
        Index("ix_product_assets_ai_run_id", "ai_run_id"),
        Index("ix_product_assets_org_status", "organization_id", "status"),
        Index("ix_product_assets_org_approval_status", "organization_id", "approval_status"),
        Index("ix_product_assets_marketplace_id", "marketplace_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="upload")
    # Self-referential: the asset this row was processed/generated from (upload -> processed, or ai_generated -> processed).
    derived_from_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_assets.id", ondelete="SET NULL"), nullable=True
    )
    ai_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_runs.id", ondelete="SET NULL"), nullable=True
    )
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="image")
    marketplace_id: Mapped[int | None] = mapped_column(SmallInteger, ForeignKey("marketplaces.id"), nullable=True)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ready")
    # Human-review gate, independent of `status` (which tracks whether the
    # file itself is ready). Uploads default to 'not_required' -- a human
    # already chose to upload them. AI-generated/processed assets are created
    # as 'pending_review' and only become primary-eligible once 'approved'.
    approval_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="not_required")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    organization: Mapped["Organization"] = relationship(back_populates="product_assets")
    product: Mapped["Product"] = relationship(back_populates="assets")
    derived_from: Mapped["ProductAsset | None"] = relationship(
        remote_side="ProductAsset.id", back_populates="derived_assets"
    )
    derived_assets: Mapped[list["ProductAsset"]] = relationship(back_populates="derived_from")
    ai_run: Mapped["AIRun | None"] = relationship(back_populates="generated_assets")
    marketplace: Mapped["Marketplace | None"] = relationship(back_populates="asset_variants")
