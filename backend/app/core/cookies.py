from fastapi import Response

from app.core.config import settings

# SameSite is a fixed architectural choice (Lax), not an environment setting —
# only Secure varies between local http:// dev and production https://.
_COOKIE_SAMESITE = "lax"


def set_session_cookie(response: Response, token: str, max_age_seconds: int) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=max_age_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=_COOKIE_SAMESITE,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite=_COOKIE_SAMESITE,
    )


def set_csrf_cookie(response: Response, token: str, max_age_seconds: int) -> None:
    # Deliberately NOT httpOnly -- same-origin JS must be able to read this
    # value to echo it back in the X-CSRF-Token header. That's the whole
    # double-submit mechanism: a cross-site attacker's JS cannot read it.
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=token,
        max_age=max_age_seconds,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=_COOKIE_SAMESITE,
        path="/",
    )


def clear_csrf_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path="/",
        httponly=False,
        secure=settings.cookie_secure,
        samesite=_COOKIE_SAMESITE,
    )
