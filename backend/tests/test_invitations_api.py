from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import AuthToken
from app.services.auth_tokens import hash_token

SIGNUP_PASSWORD = "a-very-strong-password-123"
ACCEPT_PASSWORD = "an-accepted-password-789"


def _signup(client, email, full_name="Test User"):
    resp = client.post(
        "/api/v1/auth/signup", json={"email": email, "password": SIGNUP_PASSWORD, "full_name": full_name}
    )
    assert resp.status_code == 201
    return resp.json()


def _create_org(client, name="Invite Co"):
    resp = client.post("/api/v1/organizations", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def test_owner_can_invite(client, email_service):
    _signup(client, "owner.invites@example.com")
    org = _create_org(client)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/members/invite",
        json={"email": "invitee.one@example.com", "role_key": "member"},
    )

    assert response.status_code == 201
    assert response.json()["status"] == "invited"
    invitation_emails = [e for e in email_service.sent_emails if e.kind == "invitation"]
    assert len(invitation_emails) == 1


def test_admin_can_invite(client, make_user, make_organization, make_membership, login_as):
    owner = make_user(email="owner.for.admin@example.com")
    admin = make_user(email="admin.invites@example.com")
    org = make_organization()
    make_membership(org, owner, role_key="owner")
    make_membership(org, admin, role_key="admin")

    response = login_as(admin).post(
        f"/api/v1/organizations/{org.id}/members/invite",
        json={"email": "invitee.two@example.com", "role_key": "member"},
    )

    assert response.status_code == 201


def test_member_cannot_invite(client, make_user, make_organization, make_membership, login_as):
    member = make_user(email="member.cannot@example.com")
    org = make_organization()
    make_membership(org, member, role_key="member")

    response = login_as(member).post(
        f"/api/v1/organizations/{org.id}/members/invite",
        json={"email": "invitee.three@example.com", "role_key": "member"},
    )

    assert response.status_code == 403


def test_admin_cannot_invite_owner(client, make_user, make_organization, make_membership, login_as):
    admin = make_user(email="admin.no.owner@example.com")
    org = make_organization()
    make_membership(org, admin, role_key="admin")

    response = login_as(admin).post(
        f"/api/v1/organizations/{org.id}/members/invite",
        json={"email": "invitee.four@example.com", "role_key": "owner"},
    )

    assert response.status_code == 403


def test_invalid_role_rejected(client):
    _signup(client, "owner.badrole@example.com")
    org = _create_org(client)

    response = client.post(
        f"/api/v1/organizations/{org['id']}/members/invite",
        json={"email": "invitee.five@example.com", "role_key": "superadmin"},
    )

    assert response.status_code == 400


def test_duplicate_active_invitation_rejected(client):
    _signup(client, "owner.dupe@example.com")
    org = _create_org(client)

    first = client.post(
        f"/api/v1/organizations/{org['id']}/members/invite",
        json={"email": "invitee.six@example.com", "role_key": "member"},
    )
    second = client.post(
        f"/api/v1/organizations/{org['id']}/members/invite",
        json={"email": "invitee.six@example.com", "role_key": "admin"},
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_expired_invitation_rejected(client, db, email_service):
    _signup(client, "owner.expiry@example.com")
    org = _create_org(client)
    client.post(
        f"/api/v1/organizations/{org['id']}/members/invite",
        json={"email": "invitee.seven@example.com", "role_key": "member"},
    )
    token = [e for e in email_service.sent_emails if e.kind == "invitation"][-1].token

    row = db.query(AuthToken).filter(AuthToken.token_hash == hash_token(token)).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()

    response = client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "token": token,
            "organization_id": org["id"],
            "password": ACCEPT_PASSWORD,
            "full_name": "Invitee Seven",
        },
    )
    assert response.status_code == 400


def test_reused_invitation_rejected(client, email_service):
    _signup(client, "owner.reuse@example.com")
    org = _create_org(client)
    client.post(
        f"/api/v1/organizations/{org['id']}/members/invite",
        json={"email": "invitee.eight@example.com", "role_key": "member"},
    )
    token = [e for e in email_service.sent_emails if e.kind == "invitation"][-1].token

    first = client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "token": token,
            "organization_id": org["id"],
            "password": ACCEPT_PASSWORD,
            "full_name": "Invitee Eight",
        },
    )
    second = client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "token": token,
            "organization_id": org["id"],
            "password": ACCEPT_PASSWORD,
            "full_name": "Invitee Eight",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 400


def test_successful_acceptance_new_user(client, email_service):
    _signup(client, "owner.accept@example.com")
    org = _create_org(client)
    client.post(
        f"/api/v1/organizations/{org['id']}/members/invite",
        json={"email": "invitee.nine@example.com", "role_key": "admin"},
    )
    token = [e for e in email_service.sent_emails if e.kind == "invitation"][-1].token

    response = client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "token": token,
            "organization_id": org["id"],
            "password": ACCEPT_PASSWORD,
            "full_name": "Invitee Nine",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "active"
    assert body["role_key"] == "admin"

    me_response = client.get("/api/v1/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "invitee.nine@example.com"

    login_response = client.post(
        "/api/v1/auth/login", json={"email": "invitee.nine@example.com", "password": ACCEPT_PASSWORD}
    )
    assert login_response.status_code == 200


def test_cross_organization_invitation_protection(client, email_service):
    _signup(client, "owner.cross@example.com")
    org_a = _create_org(client, name="Org A")
    org_b = _create_org(client, name="Org B")
    client.post(
        f"/api/v1/organizations/{org_a['id']}/members/invite",
        json={"email": "invitee.ten@example.com", "role_key": "member"},
    )
    token = [e for e in email_service.sent_emails if e.kind == "invitation"][-1].token

    response = client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "token": token,
            "organization_id": org_b["id"],
            "password": ACCEPT_PASSWORD,
            "full_name": "Invitee Ten",
        },
    )

    assert response.status_code == 400
