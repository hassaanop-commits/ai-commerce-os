from __future__ import annotations

import json
import logging
from contextvars import ContextVar

# Request-scoped correlation context, read by JSONLogFormatter below on
# every log line emitted anywhere during a request, without any call site
# having to pass these explicitly. All three are set by
# app.core.request_context.RequestIDMiddleware, which runs in the request's
# actual async task -- request_id/route before the rest of the stack runs,
# organization_id (once resolved) just before the middleware's own summary
# log line.
#
# contextvars, not thread-locals -- with one important caveat: FastAPI runs
# every sync ("def", not "async def") dependency and path operation via
# starlette.concurrency.run_in_threadpool, and each such call gets its OWN
# copy of the current context (contextvars.copy_context()). Reads propagate
# down into that copy fine, but a .set() made inside one threadpool call is
# invisible everywhere else -- including the middleware that dispatched it,
# and even a sibling dependency of the same request run via its own
# separate threadpool call. That's exactly why organization_id is NOT set
# directly from app.api.deps.get_organization_membership (a sync
# dependency): it stashes the value on request.state instead (backed by the
# ASGI scope dict, shared by reference regardless of which thread touches
# it) and RequestIDMiddleware copies that into this contextvar itself, from
# its own async context, right before logging.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
organization_id_var: ContextVar[str | None] = ContextVar("organization_id", default=None)
route_var: ContextVar[str | None] = ContextVar("route", default=None)

# Attributes every stdlib LogRecord carries regardless of what was logged --
# used to separate "real" extra=... fields (e.g. status_code, duration_ms)
# from the record's own bookkeeping when flattening it to JSON below.
_STANDARD_LOG_RECORD_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "taskName",
    }
)


class JSONLogFormatter(logging.Formatter):
    """One JSON object per line. Always includes the current request's
    correlation fields (request_id/organization_id/route), read fresh from
    the contextvars above at format time -- so this works for every logger
    anywhere in the app (or a library that goes through stdlib logging)
    without any call site needing to pass them in. Anything passed via
    logging's own `extra=` kwarg (e.g. status_code, duration_ms) is folded
    in as its own JSON key.

    Deliberately stdlib-only (logging + json, both already in every Python
    install) rather than a third-party JSON logging package -- the actual
    formatting logic needed here is under 20 lines, and pulling in a
    dependency to do it would trade a well-understood ~20 lines for a
    library-version surface to track, for no real benefit at this size.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            "organization_id": organization_id_var.get(),
            "route": route_var.get(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_RECORD_ATTRS and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        # default=str: a stray non-JSON-serializable value (e.g. a UUID
        # someone passed via extra=) must never crash logging itself.
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Structured (JSON) logging for the whole application. Call once at
    process start (app.main, at import time) -- replaces whatever handlers
    the root logger has with a single stream handler using
    JSONLogFormatter, so every `logging.getLogger(...)` anywhere in the app
    emits one JSON line per record. Idempotent: safe to call more than once
    (e.g. once per test-session import of app.main) without accumulating
    duplicate handlers.
    """
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JSONLogFormatter())
    root.addHandler(handler)
    root.setLevel(level)
