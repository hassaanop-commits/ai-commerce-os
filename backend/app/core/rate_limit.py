from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException, Request, status

from app.core.config import settings

# In-memory sliding-window limiter -- the lightest thing that actually works
# for a single-instance FastAPI app. No Redis, no background worker: a
# lock-guarded dict of hit timestamps per key is enough, and adding a
# dependency (e.g. slowapi) would buy nothing beyond what ~30 lines already
# does here for exactly two keying strategies (IP, account identifier).
#
# Known, accepted limitation: state lives in process memory. It resets on
# every restart and does not coordinate across multiple instances/workers.
# That's fine for the current single-instance deployment -- not something
# this is trying to solve.


class RateLimitExceededError(Exception):
    pass


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._lock = Lock()
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, *, limit: int, window_seconds: float) -> None:
        """Record one attempt under `key` and raise if that pushes it over
        `limit` within the trailing `window_seconds`. Stale hits (older than
        the window) are pruned first, so the window actually slides rather
        than resetting in fixed buckets."""
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] < cutoff:
                hits.pop(0)
            if len(hits) >= limit:
                raise RateLimitExceededError(key)
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


# One shared limiter for every auth endpoint -- keys are namespaced per scope
# (e.g. "login:ip:...", "login:acct:...") so different endpoints/axes never
# collide, without needing a separate instance (and separate reset() call)
# per endpoint.
_auth_limiter = SlidingWindowRateLimiter()


def reset_auth_rate_limits() -> None:
    """Test-only hook (see tests/conftest.py) -- state is otherwise
    process-lifetime, which is wrong to carry across independent test runs
    that share this module."""
    _auth_limiter.reset()


def enforce_auth_rate_limit(request: Request, *, scope: str, identifier: str) -> None:
    """Throttle an auth endpoint by both client IP and account identifier
    (e.g. email), independently -- either axis tripping is enough to block
    the request. IP alone under-throttles a distributed credential-stuffing
    attempt against one account; identifier alone under-throttles a single
    attacker spraying many accounts from one IP.

    Deliberately uses the raw connection host, not app.api.http_utils.client_ip()
    -- that helper returns None for anything that doesn't parse as a real IP
    (including Starlette's TestClient, which sends the literal "testclient"),
    since it feeds a Postgres INET column. A rate-limit key only needs to be a
    stable string per connection source, not a valid IP, so using the raw
    host keeps IP-based throttling exercisable in tests instead of collapsing
    every caller onto a single None key.
    """
    ip = request.client.host if request.client is not None else "unknown"
    limit = settings.auth_rate_limit_max_attempts
    window = settings.auth_rate_limit_window_seconds

    try:
        _auth_limiter.check(f"{scope}:ip:{ip}", limit=limit, window_seconds=window)
        _auth_limiter.check(f"{scope}:acct:{identifier.strip().lower()}", limit=limit, window_seconds=window)
    except RateLimitExceededError as exc:
        # Same discipline as the AI provider/marketplace error taxonomies:
        # a fixed, safe message, never internals -- here that's the existing
        # plain-string HTTPException.detail convention already used by every
        # other error in app.api.v1.auth, not a new response shape.
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
            headers={"Retry-After": str(int(window))},
        ) from exc
