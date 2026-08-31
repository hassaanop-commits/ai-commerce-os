from __future__ import annotations

import uuid

from app.models import AuditLog


def _url(org_id, suffix=""):
    return f"/api/v1/organizations/{org_id}/marketplace-connections{suffix}"


def test_create_connection_requires_admin(client, make_user, make_organization, make_membership, login_as):
    org = make_organization()
    member = make_user()
    make_membership(org, member, role_key="member")

    response = login_as(member).post(_url(org.id), json={"marketplace_key": "manual"})

    assert response.status_code == 403


def test_create_connection_succeeds_as_admin(client, db, make_user, make_organization, make_membership, login_as):
    org = make_organization()
    admin = make_user()
    make_membership(org, admin, role_key="admin")

    response = login_as(admin).post(
        _url(org.id), json={"marketplace_key": "manual", "display_name": "Test Store"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["marketplace_key"] == "manual"
    assert body["display_name"] == "Test Store"
    assert body["status"] == "connected"
    # No field on the response schema could ever carry it, but assert the
    # obvious negative anyway -- credentials must never round-trip.
    assert "credentials_ciphertext" not in body

    events = db.query(AuditLog).filter(AuditLog.event_type == "marketplace_connection_created").all()
    assert len(events) == 1


def test_create_connection_rejects_unknown_marketplace(client, make_user, make_organization, make_membership, login_as):
    org = make_organization()
    admin = make_user()
    make_membership(org, admin, role_key="admin")

    response = login_as(admin).post(_url(org.id), json={"marketplace_key": "shopify"})

    assert response.status_code == 400


def test_list_connections_is_org_scoped(client, make_user, make_organization, make_membership, make_marketplace_connection, login_as):
    org_a = make_organization()
    org_b = make_organization()
    member = make_user()
    make_membership(org_a, member, role_key="member")
    make_membership(org_b, member, role_key="member")
    make_marketplace_connection(org_a)
    make_marketplace_connection(org_b)

    response = login_as(member).get(_url(org_a.id))

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_remove_connection_requires_admin(client, make_user, make_organization, make_membership, make_marketplace_connection, login_as):
    org = make_organization()
    member = make_user()
    make_membership(org, member, role_key="member")
    connection = make_marketplace_connection(org)

    response = login_as(member).delete(_url(org.id, f"/{connection.id}"))

    assert response.status_code == 403


def test_remove_connection_disconnects_without_deleting(client, db, make_user, make_organization, make_membership, make_marketplace_connection, login_as):
    org = make_organization()
    admin = make_user()
    make_membership(org, admin, role_key="admin")
    connection = make_marketplace_connection(org)

    response = login_as(admin).delete(_url(org.id, f"/{connection.id}"))

    assert response.status_code == 200
    assert response.json()["status"] == "disconnected"

    # The row survives -- listing it still returns the (now disconnected) connection.
    listed = login_as(admin).get(_url(org.id)).json()
    assert len(listed) == 1
    assert listed[0]["status"] == "disconnected"

    events = db.query(AuditLog).filter(AuditLog.event_type == "marketplace_connection_removed").all()
    assert len(events) == 1


def test_remove_connection_cross_org_rejected(client, make_user, make_organization, make_membership, make_marketplace_connection, login_as):
    admin = make_user()
    org_a = make_organization()
    org_b = make_organization()
    make_membership(org_a, admin, role_key="admin")
    make_membership(org_b, admin, role_key="admin")
    connection_b = make_marketplace_connection(org_b)

    response = login_as(admin).delete(_url(org_a.id, f"/{connection_b.id}"))

    assert response.status_code == 404


def test_remove_unknown_connection_rejected(client, make_user, make_organization, make_membership, login_as):
    org = make_organization()
    admin = make_user()
    make_membership(org, admin, role_key="admin")

    response = login_as(admin).delete(_url(org.id, f"/{uuid.uuid4()}"))

    assert response.status_code == 404


def test_create_connection_unauthenticated_rejected(client, make_organization):
    org = make_organization()

    response = client.post(_url(org.id), json={"marketplace_key": "manual"})

    assert response.status_code == 401
