from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import AuthToken
from app.services import auth as auth_service
from app.services.auth_tokens import hash_token

SIGNUP_PASSWORD = "a-very-strong-password-123"
NEW_PASSWORD = "a-different-strong-password-456"


def test_request_reset_for_existing_email(client, db, email_service):
    auth_service.signup(
        db, email_service, email="reset.exists@example.com", password=SIGNUP_PASSWORD, full_name="Reset Exists"
    )
    email_service.sent_emails.clear()

    response = client.post("/api/v1/auth/password/forgot", json={"email": "reset.exists@example.com"})

    assert response.status_code == 202
    reset_emails = [e for e in email_service.sent_emails if e.kind == "password_reset"]
    assert len(reset_emails) == 1


def test_request_reset_for_nonexistent_email_returns_equivalent_response(client, email_service):
    response = client.post("/api/v1/auth/password/forgot", json={"email": "nobody-here@example.com"})

    assert response.status_code == 202
    assert response.json() == {
        "detail": "If that email is registered, a password reset link has been sent."
    }
    assert len(email_service.sent_emails) == 0


def test_request_reset_response_identical_for_existing_and_nonexistent(client, db, email_service):
    auth_service.signup(
        db, email_service, email="reset.compare@example.com", password=SIGNUP_PASSWORD, full_name="Reset Compare"
    )

    existing_resp = client.post("/api/v1/auth/password/forgot", json={"email": "reset.compare@example.com"})
    nonexistent_resp = client.post("/api/v1/auth/password/forgot", json={"email": "still-nobody@example.com"})

    assert existing_resp.status_code == nonexistent_resp.status_code == 202
    assert existing_resp.json() == nonexistent_resp.json()


def test_valid_reset(client, db, email_service):
    auth_service.signup(
        db, email_service, email="reset.valid@example.com", password=SIGNUP_PASSWORD, full_name="Reset Valid"
    )
    client.post("/api/v1/auth/password/forgot", json={"email": "reset.valid@example.com"})
    token = [e for e in email_service.sent_emails if e.kind == "password_reset"][-1].token

    response = client.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": NEW_PASSWORD}
    )

    assert response.status_code == 200
    assert response.json()["email"] == "reset.valid@example.com"


def test_invalid_reset_token_rejected(client):
    response = client.post(
        "/api/v1/auth/password/reset", json={"token": "garbage", "new_password": NEW_PASSWORD}
    )
    assert response.status_code == 400


def test_expired_reset_token_rejected(client, db, email_service):
    auth_service.signup(
        db, email_service, email="reset.expired@example.com", password=SIGNUP_PASSWORD, full_name="Reset Expired"
    )
    client.post("/api/v1/auth/password/forgot", json={"email": "reset.expired@example.com"})
    token = [e for e in email_service.sent_emails if e.kind == "password_reset"][-1].token

    row = db.query(AuthToken).filter(AuthToken.token_hash == hash_token(token)).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    response = client.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert response.status_code == 400


def test_reused_reset_token_rejected(client, db, email_service):
    auth_service.signup(
        db, email_service, email="reset.reuse@example.com", password=SIGNUP_PASSWORD, full_name="Reset Reuse"
    )
    client.post("/api/v1/auth/password/forgot", json={"email": "reset.reuse@example.com"})
    token = [e for e in email_service.sent_emails if e.kind == "password_reset"][-1].token

    first = client.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": NEW_PASSWORD}
    )
    second = client.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": "yet-another-password-789"}
    )

    assert first.status_code == 200
    assert second.status_code == 400


def test_existing_sessions_revoked_after_reset(client, email_service):
    signup_resp = client.post(
        "/api/v1/auth/signup",
        json={
            "email": "reset.sessions@example.com",
            "password": SIGNUP_PASSWORD,
            "full_name": "Reset Sessions",
        },
    )
    assert signup_resp.status_code == 201
    assert client.get("/api/v1/auth/me").status_code == 200

    email_service.sent_emails.clear()
    client.post("/api/v1/auth/password/forgot", json={"email": "reset.sessions@example.com"})
    token = email_service.sent_emails[-1].token
    client.post("/api/v1/auth/password/reset", json={"token": token, "new_password": NEW_PASSWORD})

    assert client.get("/api/v1/auth/me").status_code == 401


def test_password_works_after_reset(client, db, email_service):
    auth_service.signup(
        db, email_service, email="reset.newpw@example.com", password=SIGNUP_PASSWORD, full_name="Reset New PW"
    )
    email_service.sent_emails.clear()
    client.post("/api/v1/auth/password/forgot", json={"email": "reset.newpw@example.com"})
    token = email_service.sent_emails[-1].token
    client.post("/api/v1/auth/password/reset", json={"token": token, "new_password": NEW_PASSWORD})

    old_login = client.post(
        "/api/v1/auth/login", json={"email": "reset.newpw@example.com", "password": SIGNUP_PASSWORD}
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/v1/auth/login", json={"email": "reset.newpw@example.com", "password": NEW_PASSWORD}
    )
    assert new_login.status_code == 200
