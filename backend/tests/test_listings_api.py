from __future__ import annotations

import uuid

from app.models import AuditLog


def _listings_url(org_id, product_id, suffix=""):
    return f"/api/v1/organizations/{org_id}/products/{product_id}/listings{suffix}"


def _setup(make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection, role_key="owner", title="Wireless Mouse"):
    owner = make_user()
    org = make_organization()
    make_membership(org, owner, role_key=role_key)
    product = make_product(org, title=title)
    make_primary_asset(product)
    connection = make_marketplace_connection(org)
    return owner, org, product, connection


def _create_draft(client, org, product, connection):
    return client.post(_listings_url(org.id, product.id), json={"marketplace_connection_id": str(connection.id)})


# ---- creation ---------------------------------------------------------


def test_create_listing_success(client, make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection, login_as):
    owner, org, product, connection = _setup(make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection)

    response = _create_draft(login_as(owner), org, product, connection)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["title"] == "Wireless Mouse"
    assert body["marketplace_key"] == "manual"


def test_create_listing_requires_approved_primary_asset(client, make_user, make_organization, make_membership, make_product, make_marketplace_connection, login_as):
    owner = make_user()
    org = make_organization()
    make_membership(org, owner, role_key="owner")
    product = make_product(org)
    connection = make_marketplace_connection(org)

    response = _create_draft(login_as(owner), org, product, connection)

    assert response.status_code == 409


def test_create_listing_unauthenticated_rejected(client, make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection):
    _, org, product, connection = _setup(make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection)

    response = client.post(_listings_url(org.id, product.id), json={"marketplace_connection_id": str(connection.id)})

    assert response.status_code == 401


def test_create_listing_non_member_rejected(client, make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection, login_as):
    _, org, product, connection = _setup(make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection)
    outsider = make_user()

    response = _create_draft(login_as(outsider), org, product, connection)

    assert response.status_code == 403


def test_create_listing_cross_org_product_rejected(client, make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection, login_as):
    owner = make_user()
    org_a = make_organization()
    org_b = make_organization()
    make_membership(org_a, owner, role_key="owner")
    make_membership(org_b, owner, role_key="owner")
    product_b = make_product(org_b)
    make_primary_asset(product_b)
    connection_b = make_marketplace_connection(org_b)

    response = login_as(owner).post(
        _listings_url(org_a.id, product_b.id), json={"marketplace_connection_id": str(connection_b.id)}
    )

    assert response.status_code == 404


def test_create_listing_cross_org_connection_rejected(client, make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection, login_as):
    owner = make_user()
    org_a = make_organization()
    org_b = make_organization()
    make_membership(org_a, owner, role_key="owner")
    make_membership(org_b, owner, role_key="owner")
    product_a = make_product(org_a)
    make_primary_asset(product_a)
    connection_b = make_marketplace_connection(org_b)

    response = login_as(owner).post(
        _listings_url(org_a.id, product_a.id), json={"marketplace_connection_id": str(connection_b.id)}
    )

    assert response.status_code == 404


def test_create_listing_records_audit_event(client, db, make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection, login_as):
    owner, org, product, connection = _setup(make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection)

    _create_draft(login_as(owner), org, product, connection)

    events = db.query(AuditLog).filter(AuditLog.event_type == "listing_created").all()
    assert len(events) == 1
    assert events[0].organization_id == org.id


# ---- approval -----------------------------------------------------------


def test_approve_listing_as_member(client, db, make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection, login_as):
    owner, org, product, connection = _setup(make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection, role_key="member")
    logged_in = login_as(owner)
    listing = _create_draft(logged_in, org, product, connection).json()

    response = logged_in.post(_listings_url(org.id, product.id, f"/{listing['id']}/approve"))

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    events = db.query(AuditLog).filter(AuditLog.event_type == "listing_approved").all()
    assert len(events) == 1


def test_approve_non_draft_rejected(client, make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection, login_as):
    owner, org, product, connection = _setup(make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection)
    logged_in = login_as(owner)
    listing = _create_draft(logged_in, org, product, connection).json()
    logged_in.post(_listings_url(org.id, product.id, f"/{listing['id']}/approve"))

    response = logged_in.post(_listings_url(org.id, product.id, f"/{listing['id']}/approve"))

    assert response.status_code == 409


# ---- publish / retry / end require admin ---------------------------------


def test_publish_requires_admin(client, make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection, login_as):
    owner, org, product, connection = _setup(make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection)
    logged_in = login_as(owner)
    listing = _create_draft(logged_in, org, product, connection).json()
    logged_in.post(_listings_url(org.id, product.id, f"/{listing['id']}/approve"))

    member = make_user()
    make_membership(org, member, role_key="member")

    response = login_as(member).post(_listings_url(org.id, product.id, f"/{listing['id']}/publish"))

    assert response.status_code == 403


def test_end_requires_admin(client, make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection, login_as):
    owner, org, product, connection = _setup(make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection, role_key="admin")
    logged_in = login_as(owner)
    listing = _create_draft(logged_in, org, product, connection).json()
    logged_in.post(_listings_url(org.id, product.id, f"/{listing['id']}/approve"))
    logged_in.post(_listings_url(org.id, product.id, f"/{listing['id']}/publish"))

    member = make_user()
    make_membership(org, member, role_key="member")

    response = login_as(member).post(_listings_url(org.id, product.id, f"/{listing['id']}/end"))

    assert response.status_code == 403


def test_publish_wrong_status_rejected(client, make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection, login_as):
    owner, org, product, connection = _setup(make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection, role_key="admin")
    logged_in = login_as(owner)
    listing = _create_draft(logged_in, org, product, connection).json()

    response = logged_in.post(_listings_url(org.id, product.id, f"/{listing['id']}/publish"))

    assert response.status_code == 409


def test_publish_failure_records_error_and_audit_event(client, db, make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection, login_as):
    owner, org, product, connection = _setup(
        make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection,
        role_key="admin", title="__fail__ Widget",
    )
    logged_in = login_as(owner)
    listing = _create_draft(logged_in, org, product, connection).json()
    logged_in.post(_listings_url(org.id, product.id, f"/{listing['id']}/approve"))

    response = logged_in.post(_listings_url(org.id, product.id, f"/{listing['id']}/publish"))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"
    assert body["last_error"] == "marketplace_error"
    assert body["external_listing_id"] is None

    events = db.query(AuditLog).filter(AuditLog.event_type == "listing_publish_failed").all()
    assert len(events) == 1


def test_end_wrong_status_rejected(client, make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection, login_as):
    owner, org, product, connection = _setup(make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection, role_key="admin")
    logged_in = login_as(owner)
    listing = _create_draft(logged_in, org, product, connection).json()

    response = logged_in.post(_listings_url(org.id, product.id, f"/{listing['id']}/end"))

    assert response.status_code == 409


# ---- deletion -------------------------------------------------------------


def test_delete_draft_succeeds(client, make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection, login_as):
    owner, org, product, connection = _setup(make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection)
    logged_in = login_as(owner)
    listing = _create_draft(logged_in, org, product, connection).json()

    response = logged_in.delete(_listings_url(org.id, product.id, f"/{listing['id']}"))

    assert response.status_code == 204
    assert logged_in.get(_listings_url(org.id, product.id)).json() == []


def test_delete_non_draft_rejected(client, make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection, login_as):
    owner, org, product, connection = _setup(make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection)
    logged_in = login_as(owner)
    listing = _create_draft(logged_in, org, product, connection).json()
    logged_in.post(_listings_url(org.id, product.id, f"/{listing['id']}/approve"))

    response = logged_in.delete(_listings_url(org.id, product.id, f"/{listing['id']}"))

    assert response.status_code == 409


# ---- cross-org listing access ---------------------------------------------


def test_cross_org_listing_access_rejected(client, make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection, login_as):
    owner = make_user()
    org_a = make_organization()
    org_b = make_organization()
    make_membership(org_a, owner, role_key="owner")
    make_membership(org_b, owner, role_key="owner")
    product_b = make_product(org_b)
    make_primary_asset(product_b)
    connection_b = make_marketplace_connection(org_b)
    logged_in = login_as(owner)
    listing_b = _create_draft(logged_in, org_b, product_b, connection_b).json()

    # Same real listing/product ids, but requested through org A's URL --
    # must not resolve, even though the caller is a genuine owner of org A too.
    approve_response = logged_in.post(_listings_url(org_a.id, product_b.id, f"/{listing_b['id']}/approve"))
    assert approve_response.status_code == 404


def test_list_listings_unknown_product_returns_empty(client, make_user, make_organization, make_membership, login_as):
    owner = make_user()
    org = make_organization()
    make_membership(org, owner, role_key="owner")

    response = login_as(owner).get(_listings_url(org.id, uuid.uuid4()))

    assert response.status_code == 200
    assert response.json() == []


# ---- full lifecycle via the API (mirrors the manual E2E script) -----------


def test_full_listing_lifecycle_via_api(client, db, make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection, login_as):
    owner, org, product, connection = _setup(make_user, make_organization, make_membership, make_product, make_primary_asset, make_marketplace_connection, role_key="owner")
    logged_in = login_as(owner)

    draft = _create_draft(logged_in, org, product, connection).json()
    assert draft["status"] == "draft"

    approved = logged_in.post(_listings_url(org.id, product.id, f"/{draft['id']}/approve")).json()
    assert approved["status"] == "approved"

    active = logged_in.post(_listings_url(org.id, product.id, f"/{draft['id']}/publish")).json()
    assert active["status"] == "active"
    assert active["external_listing_id"] is not None
    assert active["marketplace_url"] is not None

    ended = logged_in.post(_listings_url(org.id, product.id, f"/{draft['id']}/end")).json()
    assert ended["status"] == "ended"

    for event_type in ("listing_created", "listing_approved", "listing_published", "listing_ended"):
        assert db.query(AuditLog).filter(AuditLog.event_type == event_type).count() == 1
