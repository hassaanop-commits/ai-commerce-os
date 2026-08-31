from __future__ import annotations

from app.models import AuditLog

SIGNUP_PASSWORD = "a-very-strong-password-123"


def _last_event(db, event_type):
    return (
        db.query(AuditLog)
        .filter(AuditLog.event_type == event_type)
        .order_by(AuditLog.created_at.desc())
        .first()
    )


def test_signup_creates_audit_event(client, db):
    resp = client.post(
        "/api/v1/auth/signup",
        json={"email": "audit.signup@example.com", "password": SIGNUP_PASSWORD, "full_name": "Audit Signup"},
    )
    user_id = resp.json()["id"]

    event = _last_event(db, "signup")

    assert event is not None
    assert str(event.actor_user_id) == user_id
    assert event.organization_id is not None


def test_successful_login_creates_audit_event(client, db):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "audit.login@example.com", "password": SIGNUP_PASSWORD, "full_name": "Audit Login"},
    )
    login_resp = client.post(
        "/api/v1/auth/login", json={"email": "audit.login@example.com", "password": SIGNUP_PASSWORD}
    )

    event = _last_event(db, "login_succeeded")

    assert event is not None
    assert str(event.actor_user_id) == login_resp.json()["id"]


def test_failed_login_creates_audit_event_with_nullable_actor(client, db):
    response = client.post(
        "/api/v1/auth/login", json={"email": "nobody.audit@example.com", "password": "wrong-password-123"}
    )
    assert response.status_code == 401

    event = _last_event(db, "login_failed")

    assert event is not None
    assert event.actor_user_id is None
    assert event.metadata_["email"] == "nobody.audit@example.com"


def test_logout_creates_audit_event(client, db):
    resp = client.post(
        "/api/v1/auth/signup",
        json={"email": "audit.logout@example.com", "password": SIGNUP_PASSWORD, "full_name": "Audit Logout"},
    )
    user_id = resp.json()["id"]

    client.post("/api/v1/auth/logout")

    event = _last_event(db, "logout")

    assert event is not None
    assert str(event.actor_user_id) == user_id


def test_password_reset_flow_creates_audit_events(client, db, email_service):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "audit.reset@example.com", "password": SIGNUP_PASSWORD, "full_name": "Audit Reset"},
    )
    email_service.sent_emails.clear()

    client.post("/api/v1/auth/password/forgot", json={"email": "audit.reset@example.com"})
    requested_event = _last_event(db, "password_reset_requested")
    assert requested_event is not None
    assert requested_event.actor_user_id is not None

    token = email_service.sent_emails[-1].token
    client.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": "a-new-strong-password-456"}
    )
    completed_event = _last_event(db, "password_reset_completed")
    assert completed_event is not None


def test_email_verification_creates_audit_event(client, db, email_service):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "audit.verify@example.com", "password": SIGNUP_PASSWORD, "full_name": "Audit Verify"},
    )
    token = [e for e in email_service.sent_emails if e.kind == "verification"][-1].token

    client.post("/api/v1/auth/email/verify", json={"token": token})

    event = _last_event(db, "email_verified")
    assert event is not None


def test_organization_creation_creates_audit_event(client, db):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "audit.org@example.com", "password": SIGNUP_PASSWORD, "full_name": "Audit Org"},
    )
    create_resp = client.post("/api/v1/organizations", json={"name": "Audited Org"})

    event = _last_event(db, "organization_created")

    assert event is not None
    assert str(event.organization_id) == create_resp.json()["id"]


def test_invitation_and_member_events_create_audit_events(client, db, email_service):
    client.post(
        "/api/v1/auth/signup",
        json={"email": "audit.owner@example.com", "password": SIGNUP_PASSWORD, "full_name": "Audit Owner"},
    )
    org_resp = client.post("/api/v1/organizations", json={"name": "Audit Members Co"})
    org_id = org_resp.json()["id"]

    invite_resp = client.post(
        f"/api/v1/organizations/{org_id}/members/invite",
        json={"email": "audit.invitee@example.com", "role_key": "member"},
    )
    assert _last_event(db, "member_invited") is not None
    member_id = invite_resp.json()["id"]

    token = [e for e in email_service.sent_emails if e.kind == "invitation"][-1].token
    client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "token": token,
            "organization_id": org_id,
            "password": "an-accepted-password-789",
            "full_name": "Audit Invitee",
        },
    )
    assert _last_event(db, "invitation_accepted") is not None

    # Accepting the invite swapped the client's session to the invitee's --
    # switch back to the owner's session to change the role / remove them.
    owner_login = client.post(
        "/api/v1/auth/login", json={"email": "audit.owner@example.com", "password": SIGNUP_PASSWORD}
    )
    assert owner_login.status_code == 200

    role_resp = client.patch(
        f"/api/v1/organizations/{org_id}/members/{member_id}", json={"role_key": "admin"}
    )
    assert role_resp.status_code == 200
    role_event = _last_event(db, "member_role_changed")
    assert role_event is not None
    assert role_event.metadata_["new_role_key"] == "admin"

    remove_resp = client.delete(f"/api/v1/organizations/{org_id}/members/{member_id}")
    assert remove_resp.status_code == 204
    assert _last_event(db, "member_removed") is not None


def test_sensitive_values_never_stored_in_audit_metadata(client, db):
    password = "super-secret-password-999"
    client.post(
        "/api/v1/auth/signup",
        json={"email": "audit.sensitive@example.com", "password": password, "full_name": "Audit Sensitive"},
    )

    events = db.query(AuditLog).all()
    assert len(events) > 0

    forbidden_keys = {"password", "hashed_password", "token", "raw_token", "session_token", "csrf_token"}
    for event in events:
        assert not (forbidden_keys & set(event.metadata_.keys()))
        for value in event.metadata_.values():
            assert password not in str(value)
