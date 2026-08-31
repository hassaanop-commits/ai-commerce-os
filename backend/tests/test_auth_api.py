from __future__ import annotations

from app.core.config import settings
from app.services import auth as auth_service

SIGNUP_PASSWORD = "a-very-strong-password-123"


def _signup_payload(email="new.user@example.com", password=SIGNUP_PASSWORD, full_name="New User"):
    return {"email": email, "password": password, "full_name": full_name}


# ---- signup -------------------------------------------------------------------


def test_signup_success(client):
    response = client.post("/api/v1/auth/signup", json=_signup_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new.user@example.com"
    assert body["full_name"] == "New User"
    assert "password" not in body
    assert "hashed_password" not in body

    set_cookie = response.headers.get("set-cookie", "")
    assert settings.session_cookie_name in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()

    me_response = client.get("/api/v1/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "new.user@example.com"


def test_signup_normalizes_email_case(client):
    response = client.post("/api/v1/auth/signup", json=_signup_payload(email="Mixed.Case@Example.com"))

    assert response.status_code == 201
    assert response.json()["email"] == "mixed.case@example.com"


def test_signup_duplicate_email_returns_generic_conflict(client):
    payload = _signup_payload(email="dupe@example.com")
    first = client.post("/api/v1/auth/signup", json=payload)
    assert first.status_code == 201

    second = client.post("/api/v1/auth/signup", json=payload)

    assert second.status_code == 409
    assert "password" not in second.text.lower()
    assert "hash" not in second.text.lower()


def test_signup_rejects_short_password(client):
    response = client.post("/api/v1/auth/signup", json=_signup_payload(password="short"))
    assert response.status_code == 422


def test_signup_creates_owner_membership(client):
    client.post("/api/v1/auth/signup", json=_signup_payload(email="owner.check@example.com"))

    orgs_response = client.get("/api/v1/organizations")

    assert orgs_response.status_code == 200
    orgs = orgs_response.json()
    assert len(orgs) == 1
    assert orgs[0]["role_key"] == "owner"


# ---- login ----------------------------------------------------------------------


def test_login_success(client, db, email_service):
    auth_service.signup(
        db, email_service, email="login.user@example.com", password=SIGNUP_PASSWORD, full_name="Login User"
    )

    response = client.post(
        "/api/v1/auth/login", json={"email": "login.user@example.com", "password": SIGNUP_PASSWORD}
    )

    assert response.status_code == 200
    assert response.json()["email"] == "login.user@example.com"
    assert settings.session_cookie_name in response.headers.get("set-cookie", "")

    me_response = client.get("/api/v1/auth/me")
    assert me_response.status_code == 200


def test_login_wrong_password(client, db, email_service):
    auth_service.signup(
        db, email_service, email="wrongpw@example.com", password=SIGNUP_PASSWORD, full_name="Wrong PW"
    )

    response = client.post(
        "/api/v1/auth/login", json={"email": "wrongpw@example.com", "password": "not-the-password-123"}
    )

    assert response.status_code == 401


def test_login_nonexistent_account_matches_wrong_password_response(client, db, email_service):
    auth_service.signup(
        db, email_service, email="exists@example.com", password=SIGNUP_PASSWORD, full_name="Exists"
    )

    wrong_password_resp = client.post(
        "/api/v1/auth/login", json={"email": "exists@example.com", "password": "not-the-password-123"}
    )
    nonexistent_resp = client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "not-the-password-123"}
    )

    assert wrong_password_resp.status_code == nonexistent_resp.status_code == 401
    assert wrong_password_resp.json() == nonexistent_resp.json()


# ---- /auth/me ---------------------------------------------------------------------


def test_me_without_session_rejected(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


# ---- logout -------------------------------------------------------------------------


def test_logout_revokes_session(client):
    client.post("/api/v1/auth/signup", json=_signup_payload(email="logout.user@example.com"))

    logout_response = client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 204

    me_response = client.get("/api/v1/auth/me")
    assert me_response.status_code == 401


def test_logout_is_safe_to_call_repeatedly(client):
    client.post("/api/v1/auth/signup", json=_signup_payload(email="logout.twice@example.com"))

    first = client.post("/api/v1/auth/logout")
    second = client.post("/api/v1/auth/logout")

    assert first.status_code == 204
    # The session is already revoked by the first call, so the second is
    # correctly treated as unauthenticated -- not a server error.
    assert second.status_code == 401
