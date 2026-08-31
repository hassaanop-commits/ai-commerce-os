from __future__ import annotations

import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings

CSRF_HEADER_NAME = "X-CSRF-Token"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit CSRF check for cookie-authenticated, state-changing requests.

    Enforcement is gated on the csrf_token cookie's presence rather than a
    path allowlist: if the browser has never been issued one -- a fully
    anonymous request, e.g. signup, login, or a public token-based endpoint
    with no prior session -- there is no ambient cookie-based session for a
    forged cross-site request to exploit, so the check is a no-op. The moment
    a session (and its paired csrf_token) exists, every state-changing
    request must echo the cookie's value back in the X-CSRF-Token header,
    regardless of which endpoint it targets.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method in _SAFE_METHODS:
            return await call_next(request)

        cookie_token = request.cookies.get(settings.csrf_cookie_name)
        if cookie_token is None:
            return await call_next(request)

        header_token = request.headers.get(CSRF_HEADER_NAME)
        if not header_token or not secrets.compare_digest(header_token, cookie_token):
            return JSONResponse({"detail": "Missing or invalid CSRF token."}, status_code=403)

        return await call_next(request)
