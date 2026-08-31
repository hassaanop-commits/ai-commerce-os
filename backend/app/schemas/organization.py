from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, EmailStr, Field

if TYPE_CHECKING:
    from app.models import OrganizationMember


class OrganizationMembershipRead(BaseModel):
    organization_id: uuid.UUID
    name: str
    slug: str
    role_key: str
    role_name: str
    joined_at: datetime | None

    model_config = {"from_attributes": True}


class OrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class OrganizationRead(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MemberInviteRequest(BaseModel):
    email: EmailStr
    role_key: str


class MemberRoleUpdateRequest(BaseModel):
    role_key: str


class MemberRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    role_key: str
    role_name: str
    status: str
    invited_at: datetime | None
    joined_at: datetime | None

    model_config = {"from_attributes": True}

    @classmethod
    def from_membership(cls, membership: "OrganizationMember") -> "MemberRead":
        return cls(
            id=membership.id,
            user_id=membership.user_id,
            email=membership.user.email,
            full_name=membership.user.full_name,
            role_key=membership.role.key,
            role_name=membership.role.name,
            status=membership.status,
            invited_at=membership.invited_at,
            joined_at=membership.joined_at,
        )


class InvitationAcceptRequest(BaseModel):
    token: str
    organization_id: uuid.UUID
    password: str | None = Field(default=None, min_length=12, max_length=200)
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
