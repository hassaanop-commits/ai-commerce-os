from __future__ import annotations

import re
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm import joinedload

from app.core.security import hash_password
from app.models import Organization, OrganizationMember, Role, User
from app.services.auth_tokens import INVITE_ACCEPT_TTL, consume_auth_token, create_auth_token


class InvalidRoleError(Exception):
    pass


class InsufficientPermissionError(Exception):
    pass


class AlreadyMemberError(Exception):
    pass


class DuplicateInvitationError(Exception):
    pass


class LastOwnerError(Exception):
    pass


class InvalidInvitationError(Exception):
    pass


class PasswordRequiredError(Exception):
    pass


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "workspace"


def generate_unique_slug(db: DBSession, base_text: str) -> str:
    base = _slugify(base_text)[:70]
    slug = base
    while db.query(Organization).filter(Organization.slug == slug).one_or_none() is not None:
        slug = f"{base}-{secrets.token_hex(3)}"[:80]
    return slug


def create_organization(db: DBSession, name: str, created_by: User) -> Organization:
    organization = Organization(
        name=name,
        slug=generate_unique_slug(db, name),
        created_by_user_id=created_by.id,
    )
    db.add(organization)
    db.flush()
    return organization


def add_member(
    db: DBSession,
    organization: Organization,
    user: User,
    role_key: str,
    status: str = "active",
) -> OrganizationMember:
    role = db.query(Role).filter(Role.key == role_key).one()
    membership = OrganizationMember(
        organization_id=organization.id,
        user_id=user.id,
        role_id=role.id,
        status=status,
        joined_at=datetime.now(timezone.utc) if status == "active" else None,
    )
    db.add(membership)
    db.flush()
    return membership


def list_active_memberships(db: DBSession, user: User) -> list[OrganizationMember]:
    return (
        db.query(OrganizationMember)
        .options(joinedload(OrganizationMember.organization), joinedload(OrganizationMember.role))
        .filter(OrganizationMember.user_id == user.id, OrganizationMember.status == "active")
        .order_by(OrganizationMember.joined_at)
        .all()
    )


def get_membership_by_id(
    db: DBSession, organization_id: uuid.UUID, membership_id: uuid.UUID
) -> OrganizationMember | None:
    return (
        db.query(OrganizationMember)
        .options(joinedload(OrganizationMember.role), joinedload(OrganizationMember.user))
        .filter(
            OrganizationMember.id == membership_id,
            OrganizationMember.organization_id == organization_id,
        )
        .one_or_none()
    )


def list_members(db: DBSession, organization_id: uuid.UUID) -> list[OrganizationMember]:
    return (
        db.query(OrganizationMember)
        .options(joinedload(OrganizationMember.role), joinedload(OrganizationMember.user))
        .filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.status != "removed",
        )
        .order_by(OrganizationMember.created_at)
        .all()
    )


def count_active_owners(db: DBSession, organization_id: uuid.UUID) -> int:
    return (
        db.query(OrganizationMember)
        .join(Role, OrganizationMember.role_id == Role.id)
        .filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.status == "active",
            Role.key == "owner",
        )
        .count()
    )


def _get_role(db: DBSession, role_key: str) -> Role:
    role = db.query(Role).filter(Role.key == role_key).one_or_none()
    if role is None:
        raise InvalidRoleError(role_key)
    return role


def invite_member(
    db: DBSession,
    organization: Organization,
    inviter_membership: OrganizationMember,
    email: str,
    role_key: str,
) -> tuple[OrganizationMember, str]:
    email = email.strip().lower()
    role = _get_role(db, role_key)

    if role.rank < inviter_membership.role.rank:
        raise InsufficientPermissionError("Cannot invite a role more privileged than your own.")

    invitee = db.query(User).filter(User.email == email).one_or_none()
    if invitee is None:
        # No account yet: create a placeholder (no password, status='invited')
        # so the invite_accept auth_token has a user_id to attach to. This
        # invitee completes their account as part of accepting the invite,
        # rather than through POST /auth/signup (which would otherwise
        # collide with this placeholder's now-existing email).
        invitee = User(email=email, hashed_password=None, full_name="", status="invited")
        db.add(invitee)
        db.flush()

    membership = (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.organization_id == organization.id,
            OrganizationMember.user_id == invitee.id,
        )
        .one_or_none()
    )
    if membership is not None:
        if membership.status == "active":
            raise AlreadyMemberError()
        if membership.status == "invited":
            raise DuplicateInvitationError()
        # status == "removed": re-invite by reusing the row, since
        # uq_organization_members_org_user forbids a second row for this pair.
        membership.role_id = role.id
        membership.status = "invited"
        membership.invited_by_user_id = inviter_membership.user_id
        membership.invited_at = datetime.now(timezone.utc)
        membership.joined_at = None
    else:
        membership = OrganizationMember(
            organization_id=organization.id,
            user_id=invitee.id,
            role_id=role.id,
            status="invited",
            invited_by_user_id=inviter_membership.user_id,
            invited_at=datetime.now(timezone.utc),
        )
        db.add(membership)
    db.flush()

    _, raw_token = create_auth_token(db, invitee, purpose="invite_accept", ttl=INVITE_ACCEPT_TTL)

    return membership, raw_token


def accept_invitation(
    db: DBSession,
    raw_token: str,
    organization_id: uuid.UUID,
    password: str | None,
    full_name: str | None,
) -> tuple[User, OrganizationMember]:
    token = consume_auth_token(db, raw_token, purpose="invite_accept")
    if token is None:
        raise InvalidInvitationError()

    user = token.user
    membership = (
        db.query(OrganizationMember)
        .options(joinedload(OrganizationMember.role), joinedload(OrganizationMember.user))
        .filter(
            OrganizationMember.user_id == user.id,
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.status == "invited",
        )
        .one_or_none()
    )
    if membership is None:
        # Token is real, but not for this org, or already accepted -- same
        # generic error as an outright invalid token.
        raise InvalidInvitationError()

    if user.hashed_password is None:
        if not password:
            raise PasswordRequiredError()
        user.hashed_password = hash_password(password)
        user.status = "active"
        user.email_verified_at = datetime.now(timezone.utc)
        if full_name:
            user.full_name = full_name.strip()

    membership.status = "active"
    membership.joined_at = datetime.now(timezone.utc)

    return user, membership


def change_member_role(
    db: DBSession,
    acting_membership: OrganizationMember,
    target_membership: OrganizationMember,
    new_role_key: str,
) -> OrganizationMember:
    new_role = _get_role(db, new_role_key)
    is_owner_change = target_membership.role.key == "owner" or new_role.key == "owner"

    if is_owner_change and acting_membership.role.key != "owner":
        raise InsufficientPermissionError("Only an owner can grant or revoke ownership.")

    if target_membership.role.key == "owner" and new_role.key != "owner":
        if count_active_owners(db, target_membership.organization_id) <= 1:
            raise LastOwnerError()

    target_membership.role_id = new_role.id
    return target_membership


def remove_member(
    db: DBSession,
    acting_membership: OrganizationMember,
    target_membership: OrganizationMember,
) -> None:
    if target_membership.role.key == "owner":
        if acting_membership.role.key != "owner":
            raise InsufficientPermissionError("Only an owner can remove an owner.")
        if count_active_owners(db, target_membership.organization_id) <= 1:
            raise LastOwnerError()

    target_membership.status = "removed"
