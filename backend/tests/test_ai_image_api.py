from __future__ import annotations

import uuid

from app.models import AuditLog
from app.services import ai_runs as ai_run_service


def _generate_url(org_id, product_id):
    return f"/api/v1/organizations/{org_id}/products/{product_id}/ai/generate-image"


def _assets_url(org_id, product_id, suffix=""):
    return f"/api/v1/organizations/{org_id}/products/{product_id}/assets{suffix}"


def _approve_url(org_id, product_id, asset_id):
    return _assets_url(org_id, product_id, f"/{asset_id}/approve")


def _reject_url(org_id, product_id, asset_id):
    return _assets_url(org_id, product_id, f"/{asset_id}/reject")


def _setup(make_user, make_organization, make_membership, make_product, role_key="owner", **product_kwargs):
    owner = make_user()
    org = make_organization()
    make_membership(org, owner, role_key=role_key)
    product = make_product(org, **product_kwargs)
    return owner, org, product


# ---- generation ---------------------------------------------------------


def test_generate_image_success(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product, title="Red Mug")

    response = login_as(owner).post(_generate_url(org.id, product.id), json={"prompt": "studio photo"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["image_prompt"]
    assert body["asset"] is not None
    assert body["asset"]["approval_status"] == "pending_review"
    assert body["asset"]["is_primary"] is False
    assert body["asset"]["source"] == "ai_generated"
    assert len(body["ai_runs"]) == 2


def test_generate_image_workflow_correlation(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)

    response = login_as(owner).post(_generate_url(org.id, product.id), json={"prompt": "studio photo"})
    body = response.json()

    workflow_ids = {run["metadata"]["workflow_id"] for run in body["ai_runs"]}
    assert workflow_ids == {body["workflow_id"]}
    run_types = {run["run_type"] for run in body["ai_runs"]}
    assert run_types == {"product_image.craft_prompt", "product_image.generate"}


def test_generate_image_failure_creates_zero_assets(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)

    response = logged_in.post(_generate_url(org.id, product.id), json={"prompt": "please __fail__ this"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["asset"] is None
    assert len(body["ai_runs"]) == 1
    assert body["ai_runs"][0]["error_message"] in ai_run_service.SANITIZED_ERROR_CATEGORIES

    listing = logged_in.get(_assets_url(org.id, product.id)).json()
    assert listing == []


def test_generate_image_missing_csrf_token_fails(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)

    response = login_as(owner).request(
        "POST", _generate_url(org.id, product.id), json={"prompt": "studio photo"}, skip_csrf=True
    )

    assert response.status_code == 403


def test_generate_image_unauthenticated_rejected(client, make_user, make_organization, make_membership, make_product):
    _, org, product = _setup(make_user, make_organization, make_membership, make_product)

    response = client.post(_generate_url(org.id, product.id), json={"prompt": "studio photo"})

    assert response.status_code == 401


def test_generate_image_non_member_rejected(client, make_user, make_organization, make_membership, make_product, login_as):
    _, org, product = _setup(make_user, make_organization, make_membership, make_product)
    outsider = make_user()

    response = login_as(outsider).post(_generate_url(org.id, product.id), json={"prompt": "studio photo"})

    assert response.status_code == 403


def test_generate_image_cross_org_product_rejected(client, make_user, make_organization, make_membership, make_product, login_as):
    owner = make_user()
    org_a = make_organization()
    org_b = make_organization()
    make_membership(org_a, owner, role_key="owner")
    make_membership(org_b, owner, role_key="owner")
    product_b = make_product(org_b)

    response = login_as(owner).post(_generate_url(org_a.id, product_b.id), json={"prompt": "studio photo"})

    assert response.status_code == 404


def test_generate_image_asset_exposes_prompt_and_run_id(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)

    response = login_as(owner).post(_generate_url(org.id, product.id), json={"prompt": "studio photo"})

    body = response.json()
    asset = body["asset"]
    assert asset["image_prompt"] == body["image_prompt"]
    assert asset["ai_run_id"] is not None
    assert asset["derived_from_asset_id"] is None

    generate_run = next(r for r in body["ai_runs"] if r["run_type"] == "product_image.generate")
    assert asset["ai_run_id"] == generate_run["id"]


def test_uploaded_asset_has_no_image_prompt(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    import io

    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 128

    response = login_as(owner).post(
        _assets_url(org.id, product.id),
        files={"file": ("photo.jpg", io.BytesIO(fake_jpeg), "image/jpeg")},
        data={"is_primary": "false"},
    )

    body = response.json()
    assert body["image_prompt"] is None
    assert body["ai_run_id"] is None


def test_generate_image_records_audit_event(client, db, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)

    login_as(owner).post(_generate_url(org.id, product.id), json={"prompt": "studio photo"})

    events = db.query(AuditLog).filter(AuditLog.event_type == "product_ai_image_generated").all()
    assert len(events) == 1
    assert events[0].target_id == product.id


def test_generate_image_failure_records_audit_event(client, db, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)

    login_as(owner).post(_generate_url(org.id, product.id), json={"prompt": "please __fail__ this"})

    events = db.query(AuditLog).filter(AuditLog.event_type == "product_ai_image_failed").all()
    assert len(events) == 1


# ---- approval -------------------------------------------------------------


def _generate_pending_asset(client, owner, org, product):
    logged_in = client
    body = logged_in.post(_generate_url(org.id, product.id), json={"prompt": "studio photo"}).json()
    return body["asset"]


def test_approve_requires_admin(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)
    asset = _generate_pending_asset(logged_in, owner, org, product)

    member = make_user()
    make_membership(org, member, role_key="member")

    response = login_as(member).post(_approve_url(org.id, product.id, asset["id"]))

    assert response.status_code == 403


def test_approve_success_as_admin(client, db, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product, role_key="admin")
    logged_in = login_as(owner)
    asset = _generate_pending_asset(logged_in, owner, org, product)

    response = logged_in.post(_approve_url(org.id, product.id, asset["id"]))

    assert response.status_code == 200
    assert response.json()["approval_status"] == "approved"

    events = db.query(AuditLog).filter(AuditLog.event_type == "product_asset_approved").all()
    assert len(events) == 1


def test_approve_twice_rejected(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product, role_key="admin")
    logged_in = login_as(owner)
    asset = _generate_pending_asset(logged_in, owner, org, product)
    logged_in.post(_approve_url(org.id, product.id, asset["id"]))

    response = logged_in.post(_approve_url(org.id, product.id, asset["id"]))

    assert response.status_code == 409


def test_reject_success_as_admin(client, db, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product, role_key="admin")
    logged_in = login_as(owner)
    asset = _generate_pending_asset(logged_in, owner, org, product)

    response = logged_in.post(_reject_url(org.id, product.id, asset["id"]))

    assert response.status_code == 200
    assert response.json()["approval_status"] == "rejected"

    events = db.query(AuditLog).filter(AuditLog.event_type == "product_asset_rejected").all()
    assert len(events) == 1


def test_reject_does_not_delete_asset(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product, role_key="admin")
    logged_in = login_as(owner)
    asset = _generate_pending_asset(logged_in, owner, org, product)

    logged_in.post(_reject_url(org.id, product.id, asset["id"]))

    listing = logged_in.get(_assets_url(org.id, product.id)).json()
    assert len(listing) == 1
    assert listing[0]["id"] == asset["id"]
    assert listing[0]["approval_status"] == "rejected"


def test_reject_twice_rejected(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product, role_key="admin")
    logged_in = login_as(owner)
    asset = _generate_pending_asset(logged_in, owner, org, product)
    logged_in.post(_reject_url(org.id, product.id, asset["id"]))

    response = logged_in.post(_reject_url(org.id, product.id, asset["id"]))

    assert response.status_code == 409


def test_approve_unknown_asset_rejected(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product, role_key="admin")

    response = login_as(owner).post(_approve_url(org.id, product.id, uuid.uuid4()))

    assert response.status_code == 404


def test_approve_cross_org_asset_rejected(client, make_user, make_organization, make_membership, make_product, login_as):
    admin = make_user()
    org_a = make_organization()
    org_b = make_organization()
    make_membership(org_a, admin, role_key="admin")
    make_membership(org_b, admin, role_key="admin")
    product_a = make_product(org_a)
    product_b = make_product(org_b)
    logged_in = login_as(admin)

    asset_b = _generate_pending_asset(logged_in, admin, org_b, product_b)

    response = logged_in.post(_approve_url(org_a.id, product_a.id, asset_b["id"]))

    assert response.status_code == 404


# ---- primary-asset guard ---------------------------------------------------


def test_set_primary_rejected_for_pending_review_asset(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product, role_key="admin")
    logged_in = login_as(owner)
    asset = _generate_pending_asset(logged_in, owner, org, product)

    response = logged_in.patch(_assets_url(org.id, product.id, f"/{asset['id']}"), json={"is_primary": True})

    assert response.status_code == 409


def test_set_primary_succeeds_after_approval(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product, role_key="admin")
    logged_in = login_as(owner)
    asset = _generate_pending_asset(logged_in, owner, org, product)
    logged_in.post(_approve_url(org.id, product.id, asset["id"]))

    response = logged_in.patch(_assets_url(org.id, product.id, f"/{asset['id']}"), json={"is_primary": True})

    assert response.status_code == 200
    assert response.json()["is_primary"] is True


def test_set_primary_rejected_for_rejected_asset(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product, role_key="admin")
    logged_in = login_as(owner)
    asset = _generate_pending_asset(logged_in, owner, org, product)
    logged_in.post(_reject_url(org.id, product.id, asset["id"]))

    response = logged_in.patch(_assets_url(org.id, product.id, f"/{asset['id']}"), json={"is_primary": True})

    assert response.status_code == 409


# ---- regression: uploaded assets are unaffected ----------------------------


def test_uploaded_asset_regression_set_primary_still_works(client, make_user, make_organization, make_membership, make_product, login_as):
    import io

    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)
    fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 128

    upload_response = logged_in.post(
        _assets_url(org.id, product.id),
        files={"file": ("photo.jpg", io.BytesIO(fake_jpeg), "image/jpeg")},
        data={"is_primary": "false"},
    )
    assert upload_response.status_code == 201
    asset = upload_response.json()
    assert asset["approval_status"] == "not_required"

    response = logged_in.patch(_assets_url(org.id, product.id, f"/{asset['id']}"), json={"is_primary": True})

    assert response.status_code == 200
    assert response.json()["is_primary"] is True
