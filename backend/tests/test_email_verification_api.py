from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import AuthToken
from app.services.auth_tokens import PASSWORD_RESET_TTL, create_auth_token, hash_token

SIGNUP_PASSWORD = "a-very-strong-password-123"


def _signup(client, email):
    resp = client.post(
        "/api/v1/auth/signup", json={"email": email, "password": SIGNUP_PASSWORD, "full_name": "Verify Me"}
    )
    assert resp.status_code == 201
    return resp


def test_verification_success(client, email_service):
    _signup(client, "verify.success@example.com")
    token = [e for e in email_service.sent_emails if e.kind == "verification"][-1].token

    response = client.post("/api/v1/auth/email/verify", json={"token": token})

    assert response.status_code == 200
    assert response.json()["email_verified_at"] is not None


def test_invalid_token_rejected(client):
    response = client.post("/api/v1/auth/email/verify", json={"token": "not-a-real-token"})
    assert response.status_code == 400


def test_expired_token_rejected(client, db, email_service):
    _signup(client, "verify.expired@example.com")
    token = email_service.sent_emails[-1].token

    row = db.query(AuthToken).filter(AuthToken.token_hash == hash_token(token)).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    response = client.post("/api/v1/auth/email/verify", json={"token": token})
    assert response.status_code == 400


def test_reused_token_rejected(client, email_service):
    _signup(client, "verify.reuse@example.com")
    token = email_service.sent_emails[-1].token

    first = client.post("/api/v1/auth/email/verify", json={"token": token})
    second = client.post("/api/v1/auth/email/verify", json={"token": token})

    assert first.status_code == 200
    assert second.status_code == 400


def test_wrong_purpose_token_rejected(client, db, make_user):
    user = make_user(email="wrong.purpose@example.com")
    _, raw_token = create_auth_token(db, user, purpose="password_reset", ttl=PASSWORD_RESET_TTL)
    db.commit()

    response = client.post("/api/v1/auth/email/verify", json={"token": raw_token})
    assert response.status_code == 400
