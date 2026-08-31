from __future__ import annotations

import json
import logging
import uuid

import pytest

from app.core.logging import JSONLogFormatter, organization_id_var, request_id_var, route_var
from app.core.request_context import REQUEST_ID_HEADER


class _ListHandler(logging.Handler):
    """Captures formatted log lines in-memory instead of writing anywhere --
    deterministic, independent of stdout/stderr capture quirks (the app's
    real handler is constructed once at import time, before any per-test
    stdout/stderr capture fixture would be active, so asserting against a
    real stream is unreliable; attaching a handler for the duration of one
    test is not)."""

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(JSONLogFormatter())
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))

    def records(self) -> list[dict]:
        return [json.loads(line) for line in self.lines]


@pytest.fixture()
def log_capture():
    handler = _ListHandler()
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield handler
    finally:
        root.removeHandler(handler)


# ---- JSONLogFormatter (pure unit tests, no app/DB involved) --------------------


def test_formatter_produces_valid_json_with_the_expected_keys():
    formatter = JSONLogFormatter()
    record = logging.LogRecord(
        name="app.test", level=logging.INFO, pathname=__file__, lineno=1, msg="hello", args=(), exc_info=None
    )

    parsed = json.loads(formatter.format(record))

    assert parsed["message"] == "hello"
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "app.test"
    assert "timestamp" in parsed
    assert set(["request_id", "organization_id", "route"]).issubset(parsed.keys())


def test_formatter_reads_correlation_fields_from_contextvars():
    rid_token = request_id_var.set("req-123")
    org_token = organization_id_var.set("org-456")
    route_token = route_var.set("GET /api/v1/example")
    try:
        formatter = JSONLogFormatter()
        record = logging.LogRecord(
            name="app.test", level=logging.INFO, pathname=__file__, lineno=1, msg="x", args=(), exc_info=None
        )
        parsed = json.loads(formatter.format(record))
    finally:
        request_id_var.reset(rid_token)
        organization_id_var.reset(org_token)
        route_var.reset(route_token)

    assert parsed["request_id"] == "req-123"
    assert parsed["organization_id"] == "org-456"
    assert parsed["route"] == "GET /api/v1/example"


def test_formatter_defaults_correlation_fields_to_none_outside_a_request():
    assert request_id_var.get() is None
    assert organization_id_var.get() is None
    assert route_var.get() is None

    formatter = JSONLogFormatter()
    record = logging.LogRecord(
        name="app.test", level=logging.INFO, pathname=__file__, lineno=1, msg="x", args=(), exc_info=None
    )
    parsed = json.loads(formatter.format(record))

    assert parsed["request_id"] is None
    assert parsed["organization_id"] is None
    assert parsed["route"] is None


def test_formatter_includes_extra_fields():
    formatter = JSONLogFormatter()
    record = logging.LogRecord(
        name="app.test", level=logging.INFO, pathname=__file__, lineno=1, msg="x", args=(), exc_info=None
    )
    record.status_code = 200
    record.duration_ms = 12.5

    parsed = json.loads(formatter.format(record))

    assert parsed["status_code"] == 200
    assert parsed["duration_ms"] == 12.5


def test_formatter_includes_exception_info():
    formatter = JSONLogFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="app.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="failed",
            args=(),
            exc_info=sys.exc_info(),
        )

    parsed = json.loads(formatter.format(record))

    assert "ValueError" in parsed["exc_info"]
    assert "boom" in parsed["exc_info"]


def test_formatter_never_crashes_on_a_non_json_serializable_extra_value():
    formatter = JSONLogFormatter()
    record = logging.LogRecord(
        name="app.test", level=logging.INFO, pathname=__file__, lineno=1, msg="x", args=(), exc_info=None
    )
    record.some_id = uuid.uuid4()

    parsed = json.loads(formatter.format(record))

    assert isinstance(parsed["some_id"], str)


# ---- RequestIDMiddleware, wired into the real app -------------------------------


def test_request_id_is_generated_and_echoed_back(client):
    response = client.get("/health")

    assert response.status_code == 200
    request_id = response.headers.get(REQUEST_ID_HEADER)
    assert request_id
    uuid.UUID(request_id)  # a fresh, valid UUID4 was generated


def test_incoming_request_id_header_is_reused(client):
    response = client.get("/health", headers={REQUEST_ID_HEADER: "caller-supplied-id"})

    assert response.headers[REQUEST_ID_HEADER] == "caller-supplied-id"


def test_request_handled_log_line_carries_request_id_and_route(client, log_capture):
    response = client.get("/health", headers={REQUEST_ID_HEADER: "trace-me-123"})

    assert response.status_code == 200
    matches = [r for r in log_capture.records() if r["message"] == "request handled"]
    assert len(matches) == 1
    assert matches[0]["request_id"] == "trace-me-123"
    assert matches[0]["route"] == "GET /health"
    assert matches[0]["status_code"] == 200
    assert isinstance(matches[0]["duration_ms"], (int, float))


def test_request_handled_log_line_has_no_organization_id_for_a_non_org_route(client, log_capture):
    client.get("/health")

    matches = [r for r in log_capture.records() if r["message"] == "request handled"]
    assert matches[0]["organization_id"] is None


def test_request_handled_log_line_carries_organization_id_for_an_authenticated_org_route(
    client, log_capture, make_user, make_organization, make_membership, login_as
):
    owner = make_user()
    org = make_organization()
    make_membership(org, owner, role_key="owner")
    logged_in = login_as(owner)

    response = logged_in.get(f"/api/v1/organizations/{org.id}/products")

    assert response.status_code == 200
    matches = [r for r in log_capture.records() if r["message"] == "request handled"]
    assert matches[-1]["organization_id"] == str(org.id)
    assert matches[-1]["route"] == f"GET /api/v1/organizations/{org.id}/products"


def test_request_handled_log_line_has_no_organization_id_when_membership_is_rejected(
    client, log_capture, make_user, make_organization, login_as
):
    outsider = make_user()
    org = make_organization()
    logged_in = login_as(outsider)

    response = logged_in.get(f"/api/v1/organizations/{org.id}/products")

    assert response.status_code == 403
    matches = [r for r in log_capture.records() if r["message"] == "request handled"]
    assert matches[-1]["organization_id"] is None


def test_organization_id_from_one_request_never_leaks_into_the_next(
    client, log_capture, make_user, make_organization, make_membership, login_as
):
    owner = make_user()
    org = make_organization()
    make_membership(org, owner, role_key="owner")
    logged_in = login_as(owner)

    logged_in.get(f"/api/v1/organizations/{org.id}/products")
    logged_in.get("/health")

    matches = [r for r in log_capture.records() if r["message"] == "request handled"]
    assert matches[-2]["organization_id"] == str(org.id)
    assert matches[-1]["organization_id"] is None


def test_middleware_does_not_break_an_existing_authenticated_route(client, make_user, login_as):
    user = make_user()
    logged_in = login_as(user)

    response = logged_in.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == user.email
