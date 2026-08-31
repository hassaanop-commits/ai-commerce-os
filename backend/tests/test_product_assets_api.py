from __future__ import annotations

import io
import uuid

from app.services import product_assets as asset_service

FAKE_JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 128


def _assets_url(org_id, product_id, suffix=""):
    return f"/api/v1/organizations/{org_id}/products/{product_id}/assets{suffix}"


def _setup(make_user, make_organization, make_membership, make_product):
    owner = make_user()
    org = make_organization()
    make_membership(org, owner, role_key="owner")
    product = make_product(org)
    return owner, org, product


def _upload(client, org_id, product_id, content=FAKE_JPEG_BYTES, filename="photo.jpg", is_primary=False):
    files = {"file": (filename, io.BytesIO(content), "image/jpeg")}
    data = {"is_primary": "true" if is_primary else "false"}
    return client.post(_assets_url(org_id, product_id), files=files, data=data)


def test_upload_asset(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)

    response = _upload(login_as(owner), org.id, product.id)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ready"
    assert body["source"] == "upload"
    assert body["position"] == 1
    assert body["url"].startswith(f"/api/v1/organizations/{org.id}/products/{product.id}/assets/")


def test_list_assets(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)
    _upload(logged_in, org.id, product.id)
    _upload(logged_in, org.id, product.id)

    response = logged_in.get(_assets_url(org.id, product.id))

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_setting_primary_clears_previous_primary(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)
    first = _upload(logged_in, org.id, product.id, is_primary=True).json()
    second = _upload(logged_in, org.id, product.id).json()

    response = logged_in.patch(
        _assets_url(org.id, product.id, f"/{second['id']}"), json={"is_primary": True}
    )
    assert response.status_code == 200

    listing = logged_in.get(_assets_url(org.id, product.id)).json()
    primaries = [a for a in listing if a["is_primary"]]
    assert len(primaries) == 1
    assert primaries[0]["id"] == second["id"]
    assert first["id"] != second["id"]


def test_reordering_assets(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)
    first = _upload(logged_in, org.id, product.id).json()
    second = _upload(logged_in, org.id, product.id).json()
    assert first["position"] < second["position"]

    logged_in.patch(_assets_url(org.id, product.id, f"/{first['id']}"), json={"position": second["position"]})
    logged_in.patch(_assets_url(org.id, product.id, f"/{second['id']}"), json={"position": first["position"]})

    listing = logged_in.get(_assets_url(org.id, product.id)).json()
    ordered_ids = [a["id"] for a in sorted(listing, key=lambda a: a["position"])]
    assert ordered_ids == [second["id"], first["id"]]


def test_delete_asset(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)
    asset = _upload(logged_in, org.id, product.id).json()

    response = logged_in.delete(_assets_url(org.id, product.id, f"/{asset['id']}"))

    assert response.status_code == 204
    assert logged_in.get(_assets_url(org.id, product.id)).json() == []


def test_delete_asset_removes_stored_file(db, storage_service, make_user, make_organization, make_membership, make_product):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)

    storage_key = f"products/{org.id}/{product.id}/test.jpg"
    storage_service.upload(storage_key, FAKE_JPEG_BYTES, "image/jpeg")
    assert storage_service.exists(storage_key)

    asset = asset_service.create_uploaded_asset(
        db, product, storage_key=storage_key, content_type="image/jpeg"
    )
    db.commit()

    asset_service.delete_asset(db, storage_service, asset)
    db.commit()

    assert not storage_service.exists(storage_key)


def test_upload_rejects_invalid_file_content(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)

    response = _upload(
        login_as(owner), org.id, product.id, content=b"not a real image, just plain text" * 5, filename="fake.jpg"
    )

    assert response.status_code == 400


def test_upload_rejects_oversized_file(
    client, make_user, make_organization, make_membership, make_product, login_as, monkeypatch
):
    from app.core.config import settings

    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    monkeypatch.setattr(settings, "max_upload_size_bytes", 100)

    response = _upload(login_as(owner), org.id, product.id, content=FAKE_JPEG_BYTES + b"\x00" * 1000)

    assert response.status_code == 400


def test_cross_org_asset_access_rejected(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    owner = make_user()
    org_a = make_organization()
    org_b = make_organization()
    make_membership(org_a, owner, role_key="owner")
    make_membership(org_b, owner, role_key="owner")
    product_b = make_product(org_b)
    logged_in = login_as(owner)
    asset_b = _upload(logged_in, org_b.id, product_b.id).json()

    # Same real asset/product ids, but requested through org A's URL -- must
    # not resolve, even though the caller is a genuine member of org A too.
    response = logged_in.get(_assets_url(org_a.id, product_b.id, f"/{asset_b['id']}/file"))

    assert response.status_code == 404


def test_storage_keys_are_scoped_per_organization():
    from app.services.storage import generate_storage_key

    org_a, org_b, product_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    key_a = generate_storage_key(org_a, product_id, ".jpg")
    key_b = generate_storage_key(org_b, product_id, ".jpg")

    assert str(org_a) in key_a
    assert str(org_b) in key_b
    assert key_a != key_b
