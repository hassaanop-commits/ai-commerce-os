from __future__ import annotations

import ipaddress

from fastapi import Request


def client_ip(request: Request) -> str | None:
    # request.client.host isn't guaranteed to be a real IP (e.g. Starlette's
    # TestClient sends the literal string "testclient"), and this backs a
    # Postgres INET column, so anything that doesn't parse is dropped rather
    # than sent to the database.
    if request.client is None:
        return None
    try:
        ipaddress.ip_address(request.client.host)
    except ValueError:
        return None
    return request.client.host
