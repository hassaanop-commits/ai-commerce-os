from __future__ import annotations

from app.core.config import settings
from app.core.csrf import CSRF_HEADER_NAME

SIGNUP_PASSWORD = "a-very-strong-password-123"


def _signup(client, email="csrf.user@example.com"):
    resp = client.post(
        "/api/v1/auth/signup", json={"email": email, "password": SIGNUP_PASSWORD, "full_name": "CSRF User"}
    )
    assert resp.status_code == 201
    return resp


def test_valid_csrf_token_succeeds(client):
    _signup(client)

    response = client.post("/api/v1/organizations", json={"name": "CSRF Org"})

    assert response.status_code == 201


def test_missing_csrf_token_fails(client):
    _signup(client)

    response = client.request(
        "POST", "/api/v1/organizations", json={"name": "No CSRF"}, skip_csrf=True
    )

    assert response.status_code == 403


def test_invalid_csrf_token_fails(client):
    _signup(client)

    response = client.post(
        "/api/v1/organizations",
        json={"name": "Bad CSRF"},
        headers={CSRF_HEADER_NAME: "definitely-not-the-right-token"},
    )

    assert response.status_code == 403


def test_get_does_not_require_csrf(client):
    _signup(client)

    response = client.get("/api/v1/organizations")

    assert response.status_code == 200


def test_session_cookie_alone_cannot_bypass_csrf(client):
    _signup(client)

    blocked = client.request(
        "POST", "/api/v1/organizations", json={"name": "Cookie Only"}, skip_csrf=True
    )
    assert blocked.status_code == 403

    # The session itself is still perfectly valid -- this was specifically a
    # CSRF rejection, not an authentication failure.
    me_response = client.get("/api/v1/auth/me")
    assert me_response.status_code == 200


def test_csrf_token_independent_from_session_token(client):
    _signup(client)

    session_value = client.cookies.get(settings.session_cookie_name)
    csrf_value = client.cookies.get(settings.csrf_cookie_name)

    assert session_value is not None
    assert csrf_value is not None
    assert session_value != csrf_value
