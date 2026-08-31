from __future__ import annotations

import uuid

from app.models import AuditLog
from app.services import ai_runs as ai_run_service


def _generate_url(org_id, product_id):
    return f"/api/v1/organizations/{org_id}/products/{product_id}/ai/generate-description"


def _runs_url(org_id, product_id):
    return f"/api/v1/organizations/{org_id}/products/{product_id}/ai/runs"


def _apply_url(org_id, product_id, run_id):
    return f"/api/v1/organizations/{org_id}/products/{product_id}/ai/runs/{run_id}/apply-description"


def _apply_title_url(org_id, product_id, run_id):
    return f"/api/v1/organizations/{org_id}/products/{product_id}/ai/runs/{run_id}/apply-title"


def _apply_tags_url(org_id, product_id, run_id):
    return f"/api/v1/organizations/{org_id}/products/{product_id}/ai/runs/{run_id}/apply-tags"


def _setup(make_user, make_organization, make_membership, make_product, **product_kwargs):
    owner = make_user()
    org = make_organization()
    make_membership(org, owner, role_key="owner")
    product = make_product(org, **product_kwargs)
    return owner, org, product


def test_generate_description_success(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product, title="Wireless Mouse")

    response = login_as(owner).post(_generate_url(org.id, product.id))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["generated_description"]
    assert body["generated_description"].startswith("[mock:")
    assert body["analysis"]
    assert body["generated_title"]
    assert body["generated_tags"]
    assert isinstance(body["generated_tags"], list)
    assert len(body["ai_runs"]) == 4


def test_generate_description_tracks_tokens_and_cost(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)

    response = login_as(owner).post(_generate_url(org.id, product.id))

    for run in response.json()["ai_runs"]:
        assert run["status"] == "succeeded"
        assert run["input_tokens"] > 0
        assert run["output_tokens"] > 0
        assert run["cost_usd"] is not None
        assert run["provider"] == "mock"


def test_generate_description_workflow_correlation(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)

    response = login_as(owner).post(_generate_url(org.id, product.id))
    body = response.json()

    workflow_ids = {run["metadata"]["workflow_id"] for run in body["ai_runs"]}
    assert workflow_ids == {body["workflow_id"]}
    run_types = {run["run_type"] for run in body["ai_runs"]}
    assert run_types == {
        "product_content.analyze",
        "product_content.generate_description",
        "product_content.generate_title",
        "product_content.generate_tags",
    }


def test_generate_description_failed_provider_returns_sanitized_category(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product, title="__fail__ Widget")

    response = login_as(owner).post(_generate_url(org.id, product.id))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_category"] == "provider_error"
    assert body["generated_description"] is None
    assert len(body["ai_runs"]) == 1
    failed_run = body["ai_runs"][0]
    assert failed_run["status"] == "failed"
    assert failed_run["error_message"] == "provider_error"
    # Never the raw exception text -- only the closed set of sanitized categories.
    assert failed_run["error_message"] in ai_run_service.SANITIZED_ERROR_CATEGORIES


def test_generate_description_records_audit_event(
    client, db, make_user, make_organization, make_membership, make_product, login_as
):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)

    login_as(owner).post(_generate_url(org.id, product.id))

    events = db.query(AuditLog).filter(AuditLog.event_type == "product_ai_content_generated").all()
    assert len(events) == 1
    assert events[0].target_id == product.id
    assert events[0].organization_id == org.id


def test_generate_description_unauthenticated_rejected(
    client, make_user, make_organization, make_membership, make_product
):
    _, org, product = _setup(make_user, make_organization, make_membership, make_product)

    response = client.post(_generate_url(org.id, product.id))

    assert response.status_code == 401


def test_generate_description_non_member_rejected(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    _, org, product = _setup(make_user, make_organization, make_membership, make_product)
    outsider = make_user()

    response = login_as(outsider).post(_generate_url(org.id, product.id))

    assert response.status_code == 403


def test_generate_description_cross_org_product_rejected(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    owner = make_user()
    org_a = make_organization()
    org_b = make_organization()
    make_membership(org_a, owner, role_key="owner")
    make_membership(org_b, owner, role_key="owner")
    product_b = make_product(org_b)

    response = login_as(owner).post(_generate_url(org_a.id, product_b.id))

    assert response.status_code == 404


def test_list_ai_runs(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)
    logged_in.post(_generate_url(org.id, product.id))

    response = logged_in.get(_runs_url(org.id, product.id))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 4
    # Everything the AI Studio history view needs is already on this
    # response -- no separate endpoint or schema required for history.
    for run in body:
        for field in ("provider", "model", "run_type", "status", "input_tokens", "output_tokens", "cost_usd", "created_at"):
            assert field in run


def test_list_ai_runs_includes_failed_runs(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product, title="__fail__ Widget")
    logged_in = login_as(owner)
    logged_in.post(_generate_url(org.id, product.id))

    response = logged_in.get(_runs_url(org.id, product.id))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "failed"
    assert body[0]["error_message"] == "provider_error"


def test_regenerating_creates_new_runs_without_touching_previous_ones(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)

    first = logged_in.post(_generate_url(org.id, product.id)).json()
    second = logged_in.post(_generate_url(org.id, product.id)).json()

    assert first["workflow_id"] != second["workflow_id"]
    first_run_ids = {r["id"] for r in first["ai_runs"]}
    second_run_ids = {r["id"] for r in second["ai_runs"]}
    assert first_run_ids.isdisjoint(second_run_ids)

    history = logged_in.get(_runs_url(org.id, product.id)).json()
    assert len(history) == 8
    assert {r["id"] for r in history} == first_run_ids | second_run_ids
    # The first workflow's runs are still exactly as they were -- regenerate
    # never mutates prior AIRun rows.
    first_workflow_ids_in_history = {
        r["id"] for r in history if r["metadata"]["workflow_id"] == first["workflow_id"]
    }
    assert first_workflow_ids_in_history == first_run_ids


def test_list_ai_runs_unauthenticated_rejected(client, make_user, make_organization, make_membership, make_product):
    _, org, product = _setup(make_user, make_organization, make_membership, make_product)

    response = client.get(_runs_url(org.id, product.id))

    assert response.status_code == 401


def test_list_ai_runs_non_member_rejected(client, make_user, make_organization, make_membership, make_product, login_as):
    _, org, product = _setup(make_user, make_organization, make_membership, make_product)
    outsider = make_user()

    response = login_as(outsider).get(_runs_url(org.id, product.id))

    assert response.status_code == 403


def test_list_ai_runs_cross_org_rejected(client, make_user, make_organization, make_membership, make_product, login_as):
    owner = make_user()
    org_a = make_organization()
    org_b = make_organization()
    make_membership(org_a, owner, role_key="owner")
    make_membership(org_b, owner, role_key="owner")
    product_b = make_product(org_b)
    logged_in = login_as(owner)
    logged_in.post(_generate_url(org_b.id, product_b.id))

    # Same real product id, requested through org A's URL -- must not
    # resolve, even though the caller is a genuine owner of org A too.
    response = logged_in.get(_runs_url(org_a.id, product_b.id))

    assert response.status_code == 404


def test_apply_description_success(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)
    generated = logged_in.post(_generate_url(org.id, product.id)).json()
    run_id = next(r["id"] for r in generated["ai_runs"] if r["run_type"] == "product_content.generate_description")

    response = logged_in.post(_apply_url(org.id, product.id, run_id))

    assert response.status_code == 200
    body = response.json()
    assert body["description"] == generated["generated_description"]


def test_apply_description_records_audit_event(
    client, db, make_user, make_organization, make_membership, make_product, login_as
):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)
    generated = logged_in.post(_generate_url(org.id, product.id)).json()
    run_id = next(r["id"] for r in generated["ai_runs"] if r["run_type"] == "product_content.generate_description")

    logged_in.post(_apply_url(org.id, product.id, run_id))

    events = db.query(AuditLog).filter(AuditLog.event_type == "product_ai_content_applied").all()
    assert len(events) == 1
    assert events[0].target_id == product.id


def test_apply_description_rejects_run_from_another_organization(
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

    generated_b = logged_in.post(_generate_url(org_b.id, product_b.id)).json()
    run_id_from_b = next(
        r["id"] for r in generated_b["ai_runs"] if r["run_type"] == "product_content.generate_description"
    )

    # Same real run id, but requested through org A's URL.
    response = logged_in.post(_apply_url(org_a.id, product_a.id, run_id_from_b))

    assert response.status_code == 404


def test_apply_description_rejects_run_from_a_different_product(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    owner, org, product_1 = _setup(make_user, make_organization, make_membership, make_product)
    product_2 = make_product(org)
    logged_in = login_as(owner)

    generated_1 = logged_in.post(_generate_url(org.id, product_1.id)).json()
    run_id_from_product_1 = next(
        r["id"] for r in generated_1["ai_runs"] if r["run_type"] == "product_content.generate_description"
    )

    response = logged_in.post(_apply_url(org.id, product_2.id, run_id_from_product_1))

    assert response.status_code == 404


def test_apply_description_rejects_unknown_run(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)

    response = login_as(owner).post(_apply_url(org.id, product.id, uuid.uuid4()))

    assert response.status_code == 404


def test_apply_description_rejects_failed_run(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product, title="__fail__ Widget")
    logged_in = login_as(owner)
    generated = logged_in.post(_generate_url(org.id, product.id)).json()
    failed_run_id = generated["ai_runs"][0]["id"]

    response = logged_in.post(_apply_url(org.id, product.id, failed_run_id))

    assert response.status_code == 409


def _generate_and_get_run(logged_in, org_id, product_id, run_type):
    generated = logged_in.post(_generate_url(org_id, product_id)).json()
    return generated, next(r for r in generated["ai_runs"] if r["run_type"] == run_type)


def test_apply_title_success(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)
    generated, title_run = _generate_and_get_run(logged_in, org.id, product.id, "product_content.generate_title")

    response = logged_in.post(_apply_title_url(org.id, product.id, title_run["id"]))

    assert response.status_code == 200
    assert response.json()["title"] == generated["generated_title"]


def test_apply_title_records_audit_event(client, db, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)
    _, title_run = _generate_and_get_run(logged_in, org.id, product.id, "product_content.generate_title")

    logged_in.post(_apply_title_url(org.id, product.id, title_run["id"]))

    events = db.query(AuditLog).filter(AuditLog.event_type == "product_ai_content_applied").all()
    matching = [e for e in events if e.metadata_.get("field") == "title"]
    assert len(matching) == 1
    assert matching[0].target_id == product.id


def test_apply_title_rejects_run_of_the_wrong_type(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)
    _, description_run = _generate_and_get_run(logged_in, org.id, product.id, "product_content.generate_description")

    response = logged_in.post(_apply_title_url(org.id, product.id, description_run["id"]))

    assert response.status_code == 409


def test_apply_title_cross_org_rejected(client, make_user, make_organization, make_membership, make_product, login_as):
    owner = make_user()
    org_a = make_organization()
    org_b = make_organization()
    make_membership(org_a, owner, role_key="owner")
    make_membership(org_b, owner, role_key="owner")
    product_a = make_product(org_a)
    product_b = make_product(org_b)
    logged_in = login_as(owner)
    _, title_run_b = _generate_and_get_run(logged_in, org_b.id, product_b.id, "product_content.generate_title")

    response = logged_in.post(_apply_title_url(org_a.id, product_a.id, title_run_b["id"]))

    assert response.status_code == 404


def test_apply_tags_success(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)
    generated, tags_run = _generate_and_get_run(logged_in, org.id, product.id, "product_content.generate_tags")

    response = logged_in.post(_apply_tags_url(org.id, product.id, tags_run["id"]))

    assert response.status_code == 200
    assert response.json()["metadata"]["tags"] == generated["generated_tags"]
    assert isinstance(response.json()["metadata"]["tags"], list)


def test_apply_tags_preserves_other_metadata(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)
    # Give the product some unrelated metadata first -- applying tags must
    # merge into this, not clobber it.
    logged_in.patch(
        f"/api/v1/organizations/{org.id}/products/{product.id}", json={"metadata": {"custom_field": "keep-me"}}
    )
    _, tags_run = _generate_and_get_run(logged_in, org.id, product.id, "product_content.generate_tags")

    response = logged_in.post(_apply_tags_url(org.id, product.id, tags_run["id"]))

    assert response.status_code == 200
    assert response.json()["metadata"]["custom_field"] == "keep-me"
    assert "tags" in response.json()["metadata"]


def test_apply_tags_records_audit_event(client, db, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)
    _, tags_run = _generate_and_get_run(logged_in, org.id, product.id, "product_content.generate_tags")

    logged_in.post(_apply_tags_url(org.id, product.id, tags_run["id"]))

    events = db.query(AuditLog).filter(AuditLog.event_type == "product_ai_content_applied").all()
    matching = [e for e in events if e.metadata_.get("field") == "tags"]
    assert len(matching) == 1


def test_apply_tags_rejects_run_of_the_wrong_type(client, make_user, make_organization, make_membership, make_product, login_as):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    logged_in = login_as(owner)
    _, description_run = _generate_and_get_run(logged_in, org.id, product.id, "product_content.generate_description")

    response = logged_in.post(_apply_tags_url(org.id, product.id, description_run["id"]))

    assert response.status_code == 409


def test_apply_title_and_tags_unauthenticated_rejected(client, make_user, make_organization, make_membership, make_product):
    _, org, product = _setup(make_user, make_organization, make_membership, make_product)

    assert client.post(_apply_title_url(org.id, product.id, uuid.uuid4())).status_code == 401
    assert client.post(_apply_tags_url(org.id, product.id, uuid.uuid4())).status_code == 401
