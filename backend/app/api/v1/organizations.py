from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_current_user, require_admin, require_member
from app.api.http_utils import client_ip
from app.db.session import get_db
from app.models import OrganizationMember, User
from app.schemas.organization import (
    MemberInviteRequest,
    MemberRead,
    MemberRoleUpdateRequest,
    OrganizationCreateRequest,
    OrganizationMembershipRead,
    OrganizationRead,
)
from app.services import organizations as org_service
from app.services.audit import record_event
from app.services.email import EmailService, get_email_service

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("", response_model=list[OrganizationMembershipRead])
def list_my_organizations(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[DBSession, Depends(get_db)],
) -> list[OrganizationMembershipRead]:
    memberships = org_service.list_active_memberships(db, current_user)
    return [
        OrganizationMembershipRead(
            organization_id=m.organization_id,
            name=m.organization.name,
            slug=m.organization.slug,
            role_key=m.role.key,
            role_name=m.role.name,
            joined_at=m.joined_at,
        )
        for m in memberships
    ]


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreateRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[DBSession, Depends(get_db)],
) -> OrganizationRead:
    # Ownership is never taken from the request body -- the caller always
    # becomes Owner, full stop.
    organization = org_service.create_organization(db, payload.name, created_by=current_user)
    org_service.add_member(db, organization, current_user, role_key="owner", status="active")
    db.commit()
    db.refresh(organization)

    record_event(
        db,
        "organization_created",
        actor_user_id=current_user.id,
        organization_id=organization.id,
        ip_address=client_ip(request),
    )

    return OrganizationRead.model_validate(organization)


@router.get("/{org_id}/members", response_model=list[MemberRead])
def list_members(
    membership: Annotated[OrganizationMember, Depends(require_member)],
    db: Annotated[DBSession, Depends(get_db)],
) -> list[MemberRead]:
    members = org_service.list_members(db, membership.organization_id)
    return [MemberRead.from_membership(m) for m in members]


@router.post("/{org_id}/members/invite", response_model=MemberRead, status_code=status.HTTP_201_CREATED)
def invite_member(
    payload: MemberInviteRequest,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_admin)],
    db: Annotated[DBSession, Depends(get_db)],
    email_service: Annotated[EmailService, Depends(get_email_service)],
) -> MemberRead:
    try:
        new_membership, raw_token = org_service.invite_member(
            db, membership.organization, membership, payload.email, payload.role_key
        )
    except org_service.InvalidRoleError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role.") from exc
    except org_service.InsufficientPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You cannot assign this role."
        ) from exc
    except org_service.AlreadyMemberError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This user is already a member."
        ) from exc
    except org_service.DuplicateInvitationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An invitation is already pending for this email.",
        ) from exc

    db.commit()
    db.refresh(new_membership)
    email_service.send_invitation_email(new_membership.user.email, membership.organization.name, raw_token)

    record_event(
        db,
        "member_invited",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="organization_member",
        target_id=new_membership.id,
        metadata={"invited_email": new_membership.user.email, "role_key": new_membership.role.key},
        ip_address=client_ip(request),
    )

    return MemberRead.from_membership(new_membership)


@router.patch("/{org_id}/members/{member_id}", response_model=MemberRead)
def update_member_role(
    member_id: uuid.UUID,
    payload: MemberRoleUpdateRequest,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_admin)],
    db: Annotated[DBSession, Depends(get_db)],
) -> MemberRead:
    target = org_service.get_membership_by_id(db, membership.organization_id, member_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    try:
        updated = org_service.change_member_role(db, membership, target, payload.role_key)
    except org_service.InvalidRoleError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role.") from exc
    except org_service.InsufficientPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You cannot change this member's role."
        ) from exc
    except org_service.LastOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Cannot demote the last owner."
        ) from exc

    db.commit()
    db.refresh(updated)

    record_event(
        db,
        "member_role_changed",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="organization_member",
        target_id=updated.id,
        metadata={"new_role_key": updated.role.key},
        ip_address=client_ip(request),
    )

    return MemberRead.from_membership(updated)


@router.delete("/{org_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def remove_member(
    member_id: uuid.UUID,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_admin)],
    db: Annotated[DBSession, Depends(get_db)],
) -> None:
    target = org_service.get_membership_by_id(db, membership.organization_id, member_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    try:
        org_service.remove_member(db, membership, target)
    except org_service.InsufficientPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You cannot remove this member."
        ) from exc
    except org_service.LastOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Cannot remove the last owner."
        ) from exc

    db.commit()

    record_event(
        db,
        "member_removed",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="organization_member",
        target_id=target.id,
        ip_address=client_ip(request),
    )
