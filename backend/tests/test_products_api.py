from __future__ import annotations

import uuid


def _url(org_id, suffix=""):
    return f"/api/v1/organizations/{org_id}/products{suffix}"


def test_create_product(client, make_user, make_organization, make_membership, login_as):
    owner = make_user()
    org = make_organization()
    make_membership(org, owner, role_key="owner")

    response = login_as(owner).post(
        _url(org.id), json={"sku": "SKU-1", "title": "Widget", "price": 9.99, "currency": "usd"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["sku"] == "SKU-1"
    assert body["title"] == "Widget"
    assert body["status"] == "draft"
    assert body["currency"] == "USD"
    assert body["primary_asset"] is None


def test_list_products(client, make_user, make_organization, make_membership, make_product, login_as):
    owner = make_user()
    org = make_organization()
    make_membership(org, owner, role_key="owner")
    make_product(org, sku="SKU-A", title="A")
    make_product(org, sku="SKU-B", title="B")

    response = login_as(owner).get(_url(org.id))

    assert response.status_code == 200
    assert {p["sku"] for p in response.json()} == {"SKU-A", "SKU-B"}


def test_get_product(client, make_user, make_organization, make_membership, make_product, login_as):
    owner = make_user()
    org = make_organization()
    make_membership(org, owner, role_key="owner")
    product = make_product(org)

    response = login_as(owner).get(_url(org.id, f"/{product.id}"))

    assert response.status_code == 200
    assert response.json()["id"] == str(product.id)


def test_get_nonexistent_product_returns_404(client, make_user, make_organization, make_membership, login_as):
    owner = make_user()
    org = make_organization()
    make_membership(org, owner, role_key="owner")

    response = login_as(owner).get(_url(org.id, f"/{uuid.uuid4()}"))

    assert response.status_code == 404


def test_update_product(client, make_user, make_organization, make_membership, make_product, login_as):
    owner = make_user()
    org = make_organization()
    make_membership(org, owner, role_key="owner")
    product = make_product(org, title="Old title")

    response = login_as(owner).patch(
        _url(org.id, f"/{product.id}"), json={"title": "New title", "status": "active"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "New title"
    assert body["status"] == "active"


def test_update_product_rejects_invalid_status(client, make_user, make_organization, make_membership, make_product, login_as):
    owner = make_user()
    org = make_organization()
    make_membership(org, owner, role_key="owner")
    product = make_product(org)

    response = login_as(owner).patch(_url(org.id, f"/{product.id}"), json={"status": "not-a-real-status"})

    assert response.status_code == 422


def test_delete_product_is_soft_delete(client, db, make_user, make_organization, make_membership, make_product, login_as):
    owner = make_user()
    org = make_organization()
    make_membership(org, owner, role_key="owner")
    product = make_product(org)

    response = login_as(owner).delete(_url(org.id, f"/{product.id}"))
    assert response.status_code == 204

    get_response = login_as(owner).get(_url(org.id, f"/{product.id}"))
    assert get_response.status_code == 404

    db.refresh(product)
    assert product.deleted_at is not None


def test_duplicate_sku_rejected(client, make_user, make_organization, make_membership, login_as):
    owner = make_user()
    org = make_organization()
    make_membership(org, owner, role_key="owner")
    logged_in = login_as(owner)

    first = logged_in.post(_url(org.id), json={"sku": "DUPE", "title": "First"})
    second = logged_in.post(_url(org.id), json={"sku": "DUPE", "title": "Second"})

    assert first.status_code == 201
    assert second.status_code == 409


def test_unauthenticated_access_rejected(client, make_organization):
    org = make_organization()

    response = client.get(_url(org.id))

    assert response.status_code == 401


def test_non_member_access_rejected(client, make_user, make_organization, login_as):
    user = make_user()
    org = make_organization()

    response = login_as(user).get(_url(org.id))

    assert response.status_code == 403


def test_cross_org_product_access_rejected(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    owner = make_user()
    org_a = make_organization()
    org_b = make_organization()
    # Deliberately a real member of BOTH orgs, so the only thing that can
    # block access is the product/org pairing check, not membership itself.
    make_membership(org_a, owner, role_key="owner")
    make_membership(org_b, owner, role_key="owner")
    product_in_b = make_product(org_b)

    response = login_as(owner).get(_url(org_a.id, f"/{product_in_b.id}"))

    assert response.status_code == 404
