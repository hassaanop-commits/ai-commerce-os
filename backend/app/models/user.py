from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.ai_run import AIRun
    from app.models.audit_log import AuditLog
    from app.models.auth_token import AuthToken
    from app.models.organization import Organization
    from app.models.organization_member import OrganizationMember
    from app.models.session import Session


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'invited', 'disabled')", name="ck_users_status"),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    memberships: Mapped[list["OrganizationMember"]] = relationship(
        back_populates="user", foreign_keys="OrganizationMember.user_id"
    )
    sent_invitations: Mapped[list["OrganizationMember"]] = relationship(
        back_populates="invited_by", foreign_keys="OrganizationMember.invited_by_user_id"
    )
    created_organizations: Mapped[list["Organization"]] = relationship(
        back_populates="created_by", foreign_keys="Organization.created_by_user_id"
    )
    ai_runs: Mapped[list["AIRun"]] = relationship(back_populates="user")
    sessions: Mapped[list["Session"]] = relationship(back_populates="user")
    auth_tokens: Mapped[list["AuthToken"]] = relationship(back_populates="user")
    audit_log_entries: Mapped[list["AuditLog"]] = relationship(back_populates="actor")
