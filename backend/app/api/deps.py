from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.db.session import get_db
from app.models import OrganizationMember, User
from app.models import Session as SessionModel
from app.services.sessions import get_valid_session, touch_session


def get_current_session(
    db: Annotated[DBSession, Depends(get_db)],
    session_token: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
) -> SessionModel:
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    session = get_valid_session(db, session_token)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    touch_session(db, session)
    return session


def get_current_user(session: Annotated[SessionModel, Depends(get_current_session)]) -> User:
    return session.user


def get_organization_membership(
    org_id: uuid.UUID,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[DBSession, Depends(get_db)],
) -> OrganizationMember:
    membership = (
        db.query(OrganizationMember)
        .options(joinedload(OrganizationMember.role))
        .filter(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == current_user.id,
        )
        .one_or_none()
    )
    if membership is None or membership.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this organization")
    # Stashed on request.state (shared ASGI scope, not a contextvar) so it
    # survives this sync dependency's own threadpool call -- see the note in
    # app.core.logging. RequestIDMiddleware reads it back for log
    # correlation. Only reached once membership is actually verified, so a
    # request that never authenticates/authorizes into an org correctly
    # logs no organization_id rather than an unverified one.
    request.state.organization_id = str(org_id)
    return membership


def require_rank_at_most(max_rank: int):
    def _dependency(
        membership: Annotated[OrganizationMember, Depends(get_organization_membership)],
    ) -> OrganizationMember:
        if membership.role.rank > max_rank:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return membership

    return _dependency


# roles.rank: 1=owner, 2=admin, 3=member (lower rank = more privileged).
require_member = get_organization_membership
require_admin = require_rank_at_most(2)
require_owner = require_rank_at_most(1)
