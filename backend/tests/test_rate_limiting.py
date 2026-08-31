from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.rate_limit import SlidingWindowRateLimiter, enforce_auth_rate_limit


def _fake_request(host: str = "1.2.3.4") -> SimpleNamespace:
    return SimpleNamespace(client=SimpleNamespace(host=host))


# ---- SlidingWindowRateLimiter (pure unit tests, no FastAPI/DB involved) --------


def test_limiter_allows_up_to_the_limit():
    limiter = SlidingWindowRateLimiter()

    for _ in range(3):
        limiter.check("key", limit=3, window_seconds=60)


def test_limiter_blocks_once_the_limit_is_exceeded():
    from app.core.rate_limit import RateLimitExceededError

    limiter = SlidingWindowRateLimiter()
    for _ in range(3):
        limiter.check("key", limit=3, window_seconds=60)

    with pytest.raises(RateLimitExceededError):
        limiter.check("key", limit=3, window_seconds=60)


def test_limiter_keys_are_independent():
    limiter = SlidingWindowRateLimiter()
    for _ in range(3):
        limiter.check("key-a", limit=3, window_seconds=60)

    # A different key has its own, untouched budget.
    limiter.check("key-b", limit=3, window_seconds=60)


def test_limiter_window_slides(monkeypatch):
    from app.core.rate_limit import RateLimitExceededError

    limiter = SlidingWindowRateLimiter()
    now = [1000.0]
    monkeypatch.setattr("app.core.rate_limit.time.monotonic", lambda: now[0])

    for _ in range(3):
        limiter.check("key", limit=3, window_seconds=10)
    with pytest.raises(RateLimitExceededError):
        limiter.check("key", limit=3, window_seconds=10)

    # Once the window has fully elapsed, the old hits are stale and a fresh
    # attempt is allowed again -- this is what makes it a *sliding* window
    # rather than a fixed bucket that only resets at intervals.
    now[0] += 11
    limiter.check("key", limit=3, window_seconds=10)


# ---- enforce_auth_rate_limit (axis independence, sanitized response) -----------


def test_enforce_auth_rate_limit_blocks_after_max_attempts_from_one_ip():
    for _ in range(10):
        enforce_auth_rate_limit(_fake_request("9.9.9.1"), scope="login", identifier="a@example.com")

    with pytest.raises(HTTPException) as exc_info:
        enforce_auth_rate_limit(_fake_request("9.9.9.1"), scope="login", identifier="b@example.com")

    assert exc_info.value.status_code == 429
    # Sanitized, fixed message -- never raw limiter/internal detail.
    assert exc_info.value.detail == "Too many attempts. Please try again later."
    assert "Retry-After" in exc_info.value.headers


def test_enforce_auth_rate_limit_blocks_after_max_attempts_on_one_account_regardless_of_ip():
    for i in range(10):
        enforce_auth_rate_limit(_fake_request(f"10.0.0.{i}"), scope="login", identifier="victim@example.com")

    with pytest.raises(HTTPException) as exc_info:
        enforce_auth_rate_limit(_fake_request("10.0.0.99"), scope="login", identifier="victim@example.com")

    assert exc_info.value.status_code == 429


def test_enforce_auth_rate_limit_identifier_is_case_and_whitespace_normalized():
    for _ in range(10):
        enforce_auth_rate_limit(_fake_request(f"11.0.0.{_}"), scope="login", identifier="  Victim@Example.com  ")

    with pytest.raises(HTTPException):
        enforce_auth_rate_limit(_fake_request("11.0.0.99"), scope="login", identifier="victim@example.com")


def test_enforce_auth_rate_limit_scopes_are_independent():
    # Exhausting the "login" scope for this IP/account must not affect the
    # separate "signup" scope -- each auth action gets its own budget.
    for _ in range(10):
        enforce_auth_rate_limit(_fake_request("12.0.0.1"), scope="login", identifier="c@example.com")
    with pytest.raises(HTTPException):
        enforce_auth_rate_limit(_fake_request("12.0.0.1"), scope="login", identifier="c@example.com")

    # Different scope, same IP/account -- not blocked.
    enforce_auth_rate_limit(_fake_request("12.0.0.1"), scope="signup", identifier="c@example.com")


def test_enforce_auth_rate_limit_unrelated_ip_and_account_is_unaffected():
    for _ in range(10):
        enforce_auth_rate_limit(_fake_request("13.0.0.1"), scope="login", identifier="attacker@example.com")
    with pytest.raises(HTTPException):
        enforce_auth_rate_limit(_fake_request("13.0.0.1"), scope="login", identifier="attacker@example.com")

    # A genuinely unrelated caller (different IP, different account) is
    # completely unaffected by the exhausted budget above.
    enforce_auth_rate_limit(_fake_request("14.0.0.1"), scope="login", identifier="innocent@example.com")


def test_enforce_auth_rate_limit_missing_client_uses_fallback_key():
    request = SimpleNamespace(client=None)
    for _ in range(10):
        enforce_auth_rate_limit(request, scope="login", identifier="d@example.com")

    with pytest.raises(HTTPException):
        enforce_auth_rate_limit(request, scope="login", identifier="e@example.com")


# ---- Wired into the real auth endpoints (login, signup, password reset) -------


def test_login_endpoint_rate_limited_after_repeated_failures(client, monkeypatch):
    monkeypatch.setattr("app.core.rate_limit.settings.auth_rate_limit_max_attempts", 3)

    payload = {"email": "nobody@example.com", "password": "wrong-password"}
    for _ in range(3):
        response = client.post("/api/v1/auth/login", json=payload)
        assert response.status_code == 401

    response = client.post("/api/v1/auth/login", json=payload)

    assert response.status_code == 429
    assert response.json()["detail"] == "Too many attempts. Please try again later."
    assert "Retry-After" in response.headers


def test_signup_endpoint_rate_limited_after_repeated_attempts(client, monkeypatch):
    monkeypatch.setattr("app.core.rate_limit.settings.auth_rate_limit_max_attempts", 3)

    payload = {"email": "repeat.signup@example.com", "password": "a-very-strong-password-123", "full_name": "X"}
    for _ in range(3):
        response = client.post("/api/v1/auth/signup", json=payload)
        assert response.status_code in (201, 409)

    response = client.post("/api/v1/auth/signup", json=payload)

    assert response.status_code == 429


def test_password_reset_request_endpoint_rate_limited(client, monkeypatch):
    monkeypatch.setattr("app.core.rate_limit.settings.auth_rate_limit_max_attempts", 3)

    payload = {"email": "someone@example.com"}
    for _ in range(3):
        response = client.post("/api/v1/auth/password/forgot", json=payload)
        assert response.status_code == 202

    response = client.post("/api/v1/auth/password/forgot", json=payload)

    assert response.status_code == 429


def test_login_endpoint_not_rate_limited_below_the_threshold(client, monkeypatch):
    monkeypatch.setattr("app.core.rate_limit.settings.auth_rate_limit_max_attempts", 3)

    payload = {"email": "nobody-else@example.com", "password": "wrong-password"}
    for _ in range(2):
        response = client.post("/api/v1/auth/login", json=payload)
        assert response.status_code == 401
