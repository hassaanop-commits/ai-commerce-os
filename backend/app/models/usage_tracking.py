from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, Date, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.organization import Organization


class UsageTracking(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "usage_tracking"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "metric_key",
            "period_type",
            "period_start",
            name="uq_usage_tracking_org_metric_period",
        ),
        CheckConstraint("period_type IN ('day', 'month', 'billing_cycle')", name="ck_usage_tracking_period_type"),
        Index("ix_usage_tracking_org_period_start", "organization_id", "period_start"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    metric_key: Mapped[str] = mapped_column(String(60), nullable=False)
    period_type: Mapped[str] = mapped_column(String(10), nullable=False, server_default="month")
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")

    organization: Mapped["Organization"] = relationship(back_populates="usage_records")
