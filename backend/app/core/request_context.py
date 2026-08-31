from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import organization_id_var, request_id_var, route_var

REQUEST_ID_HEADER = "X-Request-ID"

logger = logging.getLogger("app.request")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assigns every request a correlation ID -- reusing an incoming
    X-Request-ID header if the caller (e.g. an upstream proxy/load balancer,
    or another service) already supplied one, otherwise generating a fresh
    UUID4 -- and publishes it and the route via the contextvars in
    app.core.logging, so every log line emitted anywhere during this
    request's handling includes them automatically. The ID is echoed back
    in the response header so a caller can correlate their own logs
    against ours.

    Also emits one structured "request handled"/"request failed" log line
    per request (method, path, status or exception, duration) -- this
    app's only access log; there's no separate access-log mechanism. Right
    before that log line, it also copies request.state.organization_id
    (stashed there by app.api.deps.get_organization_membership once
    membership is verified, if this was an org-scoped, authenticated
    request) into the organization_id contextvar -- deliberately done here,
    in this middleware's own async context, rather than having the
    dependency set the contextvar itself: FastAPI runs every sync
    dependency through starlette.concurrency.run_in_threadpool, each call
    getting its own independent copy of the current context, so a .set()
    made inside one would never be visible back out here. request.state is
    backed by the shared ASGI scope dict instead, immune to that.

    Registered after CSRFMiddleware (app.main) so it wraps outside it and
    is the outermost user middleware: the request ID/route context exists
    before CSRF (or anything else) runs, and the summary log line captures
    the final status code after everything downstream has completed.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming_id = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming_id if incoming_id else str(uuid.uuid4())
        route_label = f"{request.method} {request.url.path}"

        rid_token = request_id_var.set(request_id)
        route_token = route_var.set(route_label)
        org_token = organization_id_var.set(None)

        # The summary log line is deliberately emitted *inside* this
        # try/finally, before the contextvars are reset below -- resetting
        # first would leave the very "request handled"/"request failed"
        # line (the one line every request is guaranteed to produce) with
        # blank correlation fields, defeating the point of this middleware.
        start = time.monotonic()
        try:
            try:
                response = await call_next(request)
            except Exception:
                organization_id_var.set(getattr(request.state, "organization_id", None))
                duration_ms = round((time.monotonic() - start) * 1000, 2)
                logger.exception("request failed", extra={"duration_ms": duration_ms})
                raise

            organization_id_var.set(getattr(request.state, "organization_id", None))
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            logger.info(
                "request handled",
                extra={"status_code": response.status_code, "duration_ms": duration_ms},
            )
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            request_id_var.reset(rid_token)
            route_var.reset(route_token)
            organization_id_var.reset(org_token)
