from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.api.deps import (
    get_current_session,
    get_current_user,
    get_organization_membership,
    require_admin,
    require_member,
    require_owner,
)
from app.services.sessions import create_session, revoke_session


# ---- authentication dependency ----------------------------------------------


def test_valid_session_authenticates(db, make_user):
    user = make_user()
    _, raw_token = create_session(db, user)

    session = get_current_session(db=db, session_token=raw_token)

    assert session.user_id == user.id
    assert get_current_user(session=session).id == user.id


def test_missing_session_token_rejected(db):
    with pytest.raises(HTTPException) as exc_info:
        get_current_session(db=db, session_token=None)

    assert exc_info.value.status_code == 401


def test_expired_session_rejected(db, make_user):
    user = make_user()
    session, raw_token = create_session(db, user)
    session.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        get_current_session(db=db, session_token=raw_token)

    assert exc_info.value.status_code == 401


def test_revoked_session_rejected(db, make_user):
    user = make_user()
    session, raw_token = create_session(db, user)
    revoke_session(db, session)

    with pytest.raises(HTTPException) as exc_info:
        get_current_session(db=db, session_token=raw_token)

    assert exc_info.value.status_code == 401


def test_unknown_session_token_rejected(db):
    with pytest.raises(HTTPException) as exc_info:
        get_current_session(db=db, session_token="not-a-real-token")

    assert exc_info.value.status_code == 401


# ---- organization membership dependency -------------------------------------


def test_active_membership_returns_context(db, make_user, make_organization, make_membership):
    user = make_user()
    org = make_organization()
    membership = make_membership(org, user, role_key="member")

    result = get_organization_membership(org_id=org.id, current_user=user, db=db)

    assert result.id == membership.id
    assert result.organization_id == org.id


def test_inactive_membership_rejected(db, make_user, make_organization, make_membership):
    user = make_user()
    org = make_organization()
    make_membership(org, user, role_key="member", status="invited")

    with pytest.raises(HTTPException) as exc_info:
        get_organization_membership(org_id=org.id, current_user=user, db=db)

    assert exc_info.value.status_code == 403


def test_non_member_rejected(db, make_user, make_organization):
    user = make_user()
    org = make_organization()

    with pytest.raises(HTTPException) as exc_info:
        get_organization_membership(org_id=org.id, current_user=user, db=db)

    assert exc_info.value.status_code == 403


def test_cross_organization_access_rejected(db, make_user, make_organization, make_membership):
    user = make_user()
    org_a = make_organization()
    org_b = make_organization()
    make_membership(org_a, user, role_key="owner")

    with pytest.raises(HTTPException) as exc_info:
        get_organization_membership(org_id=org_b.id, current_user=user, db=db)

    assert exc_info.value.status_code == 403


# ---- role-based authorization -------------------------------------------------


def test_owner_authorization(db, make_user, make_organization, make_membership):
    user = make_user()
    org = make_organization()
    membership = make_membership(org, user, role_key="owner")

    assert require_owner(membership=membership).id == membership.id
    assert require_admin(membership=membership).id == membership.id
    assert require_member(org_id=org.id, current_user=user, db=db).id == membership.id


def test_admin_authorization(db, make_user, make_organization, make_membership):
    user = make_user()
    org = make_organization()
    membership = make_membership(org, user, role_key="admin")

    assert require_admin(membership=membership).id == membership.id
    with pytest.raises(HTTPException) as exc_info:
        require_owner(membership=membership)
    assert exc_info.value.status_code == 403


def test_member_authorization(db, make_user, make_organization, make_membership):
    user = make_user()
    org = make_organization()
    membership = make_membership(org, user, role_key="member")

    assert require_member(org_id=org.id, current_user=user, db=db).id == membership.id
    with pytest.raises(HTTPException) as exc_info:
        require_admin(membership=membership)
    assert exc_info.value.status_code == 403
