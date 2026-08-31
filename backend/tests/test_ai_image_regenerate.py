from __future__ import annotations

import io
import uuid

from app.models import ProductAsset


def _generate_url(org_id, product_id):
    return f"/api/v1/organizations/{org_id}/products/{product_id}/ai/generate-image"


def _regenerate_url(org_id, product_id, asset_id):
    return f"/api/v1/organizations/{org_id}/products/{product_id}/ai/assets/{asset_id}/regenerate"


def _assets_url(org_id, product_id, suffix=""):
    return f"/api/v1/organizations/{org_id}/products/{product_id}/assets{suffix}"


def _runs_url(org_id, product_id):
    return f"/api/v1/organizations/{org_id}/products/{product_id}/ai/runs"


def _setup(make_user, make_organization, make_membership, make_product, role_key="owner"):
    owner = make_user()
    org = make_organization()
    make_membership(org, owner, role_key=role_key)
    product = make_product(org)
    return owner, org, product


def _generate_asset(client, org, product):
    body = client.post(_generate_url(org.id, product.id), json={"prompt": "studio photo"}).json()
    return body["asset"]


def test_regenerate_creates_new_asset_and_preserves_original(
    client, db, make_user, make_organization, make_membership, make_product, login_as
):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)
    original = _generate_asset(logged_in, org, product)

    response = logged_in.post(_regenerate_url(org.id, product.id, original["id"]))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    new_asset = body["asset"]
    assert new_asset["id"] != original["id"]
    assert new_asset["derived_from_asset_id"] == original["id"]
    assert new_asset["approval_status"] == "pending_review"
    assert new_asset["is_primary"] is False
    assert new_asset["source"] == "ai_generated"

    # Regeneration is always exactly one slot -- index 0, succeeded, carrying
    # the new asset and no error category.
    assert len(body["variations"]) == 1
    assert body["variations"][0] == {
        "index": 0,
        "status": "succeeded",
        "asset": new_asset,
        "error_category": None,
        "error_message": None,
    }

    listing = logged_in.get(_assets_url(org.id, product.id)).json()
    ids = {a["id"] for a in listing}
    assert original["id"] in ids
    assert new_asset["id"] in ids
    assert len(listing) == 2

    # The original file/row is untouched.
    original_row = db.get(ProductAsset, uuid.UUID(original["id"]))
    assert original_row is not None
    assert original_row.approval_status == "pending_review"


def test_regenerate_reuses_the_original_crafted_prompt(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)
    original = _generate_asset(logged_in, org, product)
    assert original["image_prompt"]

    response = logged_in.post(_regenerate_url(org.id, product.id, original["id"]))

    body = response.json()
    assert body["image_prompt"] == original["image_prompt"]
    assert body["asset"]["image_prompt"] == original["image_prompt"]
    # No craft_prompt run this time -- the prompt was reused, not re-derived.
    assert all(r["run_type"] != "product_image.craft_prompt" for r in body["ai_runs"])
    assert len(body["ai_runs"]) == 1


def test_regenerate_uses_own_workflow_and_ai_run(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)
    original = _generate_asset(logged_in, org, product)
    original_run_ids = {r["id"] for r in logged_in.get(_runs_url(org.id, product.id)).json()}

    response = logged_in.post(_regenerate_url(org.id, product.id, original["id"]))

    body = response.json()
    assert body["workflow_id"]
    new_run_ids = {r["id"] for r in body["ai_runs"]}
    assert new_run_ids.isdisjoint(original_run_ids)
    assert body["asset"]["ai_run_id"] in new_run_ids


def test_regenerate_requires_independent_approval(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product, role_key="admin")
    logged_in = login_as(owner)
    original = _generate_asset(logged_in, org, product)
    logged_in.post(_assets_url(org.id, product.id, f"/{original['id']}/approve"))

    response = logged_in.post(_regenerate_url(org.id, product.id, original["id"]))
    new_asset = response.json()["asset"]

    # Approving the original never carries over to the regenerated copy.
    assert new_asset["approval_status"] == "pending_review"
    set_primary = logged_in.patch(_assets_url(org.id, product.id, f"/{new_asset['id']}"), json={"is_primary": True})
    assert set_primary.status_code == 409


def test_regenerate_rejects_uploaded_asset(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)
    fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 128
    upload = logged_in.post(
        _assets_url(org.id, product.id),
        files={"file": ("photo.jpg", io.BytesIO(fake_jpeg), "image/jpeg")},
        data={"is_primary": "false"},
    ).json()

    response = logged_in.post(_regenerate_url(org.id, product.id, upload["id"]))

    assert response.status_code == 409


def test_regenerate_unknown_asset_rejected(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)

    response = login_as(owner).post(_regenerate_url(org.id, product.id, uuid.uuid4()))

    assert response.status_code == 404


def test_regenerate_cross_org_asset_rejected(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    owner = make_user()
    org_a = make_organization()
    org_b = make_organization()
    make_membership(org_a, owner, role_key="owner")
    make_membership(org_b, owner, role_key="owner")
    product_a = make_product(org_a)
    product_b = make_product(org_b)
    logged_in = login_as(owner)
    asset_b = _generate_asset(logged_in, org_b, product_b)

    response = logged_in.post(_regenerate_url(org_a.id, product_a.id, asset_b["id"]))

    assert response.status_code == 404


def test_regenerate_unauthenticated_rejected(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    asset = _generate_asset(login_as(owner), org, product)
    client.cookies.clear()

    response = client.post(_regenerate_url(org.id, product.id, asset["id"]))

    assert response.status_code == 401


def test_regenerate_non_member_rejected(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    asset = _generate_asset(login_as(owner), org, product)
    outsider = make_user()

    response = login_as(outsider).post(_regenerate_url(org.id, product.id, asset["id"]))

    assert response.status_code == 403


def test_regenerate_failure_preserves_original_and_creates_zero_new_assets(
    client, db, make_user, make_organization, make_membership, make_product, login_as
):
    from app.ai.providers import get_default_image_provider
    from app.ai.providers.base import ProviderError
    from app.main import app

    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)
    original = _generate_asset(logged_in, org, product)

    class _AlwaysFailImageProvider:
        name = "mock-fail"

        def generate_image(self, *, prompt, model, size="1024x1024"):
            raise ProviderError("provider_error", "boom")

    app.dependency_overrides[get_default_image_provider] = lambda: _AlwaysFailImageProvider()
    try:
        response = logged_in.post(_regenerate_url(org.id, product.id, original["id"]))
    finally:
        del app.dependency_overrides[get_default_image_provider]

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["asset"] is None

    assert len(body["variations"]) == 1
    variation = body["variations"][0]
    assert variation["index"] == 0
    assert variation["status"] == "failed"
    assert variation["asset"] is None
    assert variation["error_category"] == "provider_error"
    assert variation["error_message"] == "The AI provider returned an error. Please try again."
    assert "boom" not in variation["error_message"]

    listing = logged_in.get(_assets_url(org.id, product.id)).json()
    assert len(listing) == 1
    assert listing[0]["id"] == original["id"]


def test_regenerate_records_audit_event(
    client, db, make_user, make_organization, make_membership, make_product, login_as
):
    from app.models import AuditLog

    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)
    original = _generate_asset(logged_in, org, product)

    logged_in.post(_regenerate_url(org.id, product.id, original["id"]))

    events = db.query(AuditLog).filter(AuditLog.event_type == "product_ai_image_regenerated").all()
    assert len(events) == 1
    assert events[0].metadata_["regenerated_from_asset_id"] == original["id"]
