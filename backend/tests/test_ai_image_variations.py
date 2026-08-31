from __future__ import annotations

from app.ai.providers.base import ImageResult, ProviderError
from app.models import AIRun, ProductAsset


def _generate_url(org_id, product_id):
    return f"/api/v1/organizations/{org_id}/products/{product_id}/ai/generate-image"


def _assets_url(org_id, product_id):
    return f"/api/v1/organizations/{org_id}/products/{product_id}/assets"


def _setup(make_user, make_organization, make_membership, make_product):
    owner = make_user()
    org = make_organization()
    make_membership(org, owner, role_key="owner")
    product = make_product(org)
    return owner, org, product


def test_generate_image_default_variations_is_one(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)

    response = login_as(owner).post(_generate_url(org.id, product.id), json={"prompt": "studio photo"})

    assert response.status_code == 200
    body = response.json()
    assert len(body["assets"]) == 1
    assert body["asset"]["id"] == body["assets"][0]["id"]


def test_generate_image_multiple_variations_each_own_asset_and_run(
    client, db, make_user, make_organization, make_membership, make_product, login_as
):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)

    response = login_as(owner).post(
        _generate_url(org.id, product.id), json={"prompt": "studio photo", "variations": 3}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert len(body["assets"]) == 3

    asset_ids = {a["id"] for a in body["assets"]}
    assert len(asset_ids) == 3
    for asset in body["assets"]:
        assert asset["approval_status"] == "pending_review"
        assert asset["is_primary"] is False
        assert asset["source"] == "ai_generated"

    # One craft_prompt run (shared) + one generate run per variation.
    generate_runs = [r for r in body["ai_runs"] if r["run_type"] == "product_image.generate"]
    craft_runs = [r for r in body["ai_runs"] if r["run_type"] == "product_image.craft_prompt"]
    assert len(generate_runs) == 3
    assert len(craft_runs) == 1
    workflow_ids = {r["metadata"]["workflow_id"] for r in body["ai_runs"]}
    assert workflow_ids == {body["workflow_id"]}

    stored_assets = db.query(ProductAsset).filter(ProductAsset.product_id == product.id).all()
    assert len(stored_assets) == 3
    assert all(a.approval_status == "pending_review" for a in stored_assets)
    assert all(not a.is_primary for a in stored_assets)


def test_generate_image_variations_rejects_out_of_range(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)

    too_many = login_as(owner).post(
        _generate_url(org.id, product.id), json={"prompt": "studio photo", "variations": 5}
    )
    zero = login_as(owner).post(_generate_url(org.id, product.id), json={"prompt": "studio photo", "variations": 0})

    assert too_many.status_code == 422
    assert zero.status_code == 422


class _PartialFailureProvider:
    """Fails the craft-prompt call's underlying image calls... no -- this
    fails every *other* generate_image call, to exercise "some variations
    succeed, some fail" without touching retry timing."""

    name = "mock-partial"

    def __init__(self) -> None:
        self.image_calls = 0

    def complete(self, *, system: str, prompt: str, model: str, max_tokens: int = 1024):
        from app.ai.providers.base import CompletionResult

        return CompletionResult(text=f"[prompt] {prompt[:50]}", input_tokens=5, output_tokens=5, model=model)

    def generate_image(self, *, prompt: str, model: str, size: str = "1024x1024") -> ImageResult:
        self.image_calls += 1
        if self.image_calls % 2 == 0:
            raise ProviderError("content_policy_violation", "Rejected by moderation.")
        return ImageResult(content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 128, content_type="image/png", model=model)


def test_generate_image_partial_variation_failure_still_succeeds_with_fewer_assets(
    client, db, make_user, make_organization, make_membership, make_product, login_as
):
    from app.ai.providers import get_default_image_provider
    from app.main import app

    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    provider = _PartialFailureProvider()
    app.dependency_overrides[get_default_image_provider] = lambda: provider
    try:
        response = login_as(owner).post(
            _generate_url(org.id, product.id), json={"prompt": "studio photo", "variations": 4}
        )
    finally:
        del app.dependency_overrides[get_default_image_provider]

    assert response.status_code == 200
    body = response.json()
    # 4 attempts, every other one fails -> 2 succeed.
    assert body["status"] == "succeeded"
    assert len(body["assets"]) == 2

    failed_runs = db.query(AIRun).filter(
        AIRun.related_entity_id == product.id, AIRun.status == "failed", AIRun.run_type == "product_image.generate"
    ).all()
    assert len(failed_runs) == 2
    assert all(r.error_message == "content_policy_violation" for r in failed_runs)

    # Failed variations never produced an asset -- exactly the successful count exists in the DB.
    assert db.query(ProductAsset).filter(ProductAsset.product_id == product.id).count() == 2


def test_generate_image_all_variations_fail_reports_failed_with_zero_assets(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)

    response = login_as(owner).post(
        _generate_url(org.id, product.id), json={"prompt": "please __fail__ this", "variations": 3}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["assets"] == []
    assert body["asset"] is None
    # craft_prompt itself failed here -- no image-generation attempt was ever
    # made, so there is nothing to report per slot, not even a failed one.
    assert body["variations"] == []


# ---- per-variation failure detail -------------------------------------------


def test_generate_image_single_variation_reports_one_succeeded_slot(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)

    response = login_as(owner).post(_generate_url(org.id, product.id), json={"prompt": "studio photo"})

    body = response.json()
    assert len(body["variations"]) == 1
    variation = body["variations"][0]
    assert variation["index"] == 0
    assert variation["status"] == "succeeded"
    assert variation["asset"]["id"] == body["asset"]["id"]
    assert variation["error_category"] is None
    assert variation["error_message"] is None


def test_generate_image_partial_failure_reports_per_slot_detail(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    from app.ai.providers import get_default_image_provider
    from app.main import app

    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    provider = _PartialFailureProvider()
    app.dependency_overrides[get_default_image_provider] = lambda: provider
    try:
        response = login_as(owner).post(
            _generate_url(org.id, product.id), json={"prompt": "studio photo", "variations": 4}
        )
    finally:
        del app.dependency_overrides[get_default_image_provider]

    body = response.json()
    variations = sorted(body["variations"], key=lambda v: v["index"])
    assert [v["index"] for v in variations] == [0, 1, 2, 3]
    # Odd calls (1st, 3rd) succeed; even calls (2nd, 4th) fail -- see _PartialFailureProvider.
    assert [v["status"] for v in variations] == ["succeeded", "failed", "succeeded", "failed"]

    for v in variations:
        if v["status"] == "succeeded":
            assert v["asset"] is not None
            assert v["error_category"] is None
            assert v["error_message"] is None
        else:
            assert v["asset"] is None
            assert v["error_category"] == "content_policy_violation"
            assert v["error_message"] == "The request was rejected by content moderation."

    # Every succeeded slot's asset id appears in the aggregate `assets` list too.
    succeeded_asset_ids = {v["asset"]["id"] for v in variations if v["status"] == "succeeded"}
    assert succeeded_asset_ids == {a["id"] for a in body["assets"]}


class _AlwaysFailImageProvider:
    """Text/craft-prompt succeeds; every image-generation attempt fails with
    a distinct sanitized category depending on call order, to prove each
    failed slot carries its own category rather than a single last-one-wins
    value. Deliberately uses only non-retryable categories (see
    app.ai.tools._common.RETRYABLE_ERROR_CATEGORIES) so each variation calls
    generate_image exactly once -- a retryable category here would call it
    multiple times per variation and break the call-index-based assignment.
    """

    name = "mock-always-fail"
    _categories = ["provider_not_configured", "content_policy_violation", "unknown_error"]

    def __init__(self) -> None:
        self.image_calls = 0

    def complete(self, *, system: str, prompt: str, model: str, max_tokens: int = 1024):
        from app.ai.providers.base import CompletionResult

        return CompletionResult(text=f"[prompt] {prompt[:50]}", input_tokens=5, output_tokens=5, model=model)

    def generate_image(self, *, prompt: str, model: str, size: str = "1024x1024") -> ImageResult:
        category = self._categories[self.image_calls]
        self.image_calls += 1
        raise ProviderError(category, f"boom (raw internal detail #{self.image_calls}, never expose this)")


def test_generate_image_all_generate_attempts_fail_reports_each_slot_with_its_own_category(
    client, db, make_user, make_organization, make_membership, make_product, login_as
):
    from app.ai.providers import get_default_image_provider
    from app.main import app

    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    provider = _AlwaysFailImageProvider()
    app.dependency_overrides[get_default_image_provider] = lambda: provider
    try:
        response = login_as(owner).post(
            _generate_url(org.id, product.id), json={"prompt": "studio photo", "variations": 3}
        )
    finally:
        del app.dependency_overrides[get_default_image_provider]

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["assets"] == []
    assert body["asset"] is None

    variations = sorted(body["variations"], key=lambda v: v["index"])
    assert [v["index"] for v in variations] == [0, 1, 2]
    assert all(v["status"] == "failed" for v in variations)
    assert all(v["asset"] is None for v in variations)
    # Each slot keeps its OWN category -- not collapsed to a single value.
    assert [v["error_category"] for v in variations] == [
        "provider_not_configured",
        "content_policy_violation",
        "unknown_error",
    ]
    assert variations[0]["error_message"] == "AI provider is not configured."
    assert variations[1]["error_message"] == "The request was rejected by content moderation."
    assert variations[2]["error_message"] == "AI generation failed. Please try again."


class _UnsafeMessageImageProvider:
    """A deliberately misbehaving provider whose ProviderError message
    contains request/response-shaped detail that must NEVER be echoed back
    to a client -- see app.ai.providers.base.ProviderError: "The original
    exception ... is available on __cause__ for server-side logging only".
    Every real provider in this codebase (OpenAI/Anthropic/Gemini) only ever
    raises hardcoded, developer-authored safe strings; this simulates a
    provider that violates that contract, to prove the *response layer*
    doesn't depend on providers behaving -- the per-variation error_message
    is structurally incapable of reflecting it, because it's always looked
    up from the fixed category table (app.services.ai_runs.describe_error_category),
    never built from the exception text itself.
    """

    name = "mock-unsafe"

    def complete(self, *, system: str, prompt: str, model: str, max_tokens: int = 1024):
        from app.ai.providers.base import CompletionResult

        return CompletionResult(text=f"[prompt] {prompt[:50]}", input_tokens=5, output_tokens=5, model=model)

    def generate_image(self, *, prompt: str, model: str, size: str = "1024x1024") -> ImageResult:
        raise ProviderError(
            "provider_error", "traceback: sk-live-fAkEsEcReT api_key=leaked at internal-host:8443/v1/images"
        )


def test_generate_image_variation_error_message_is_never_provider_supplied_text(
    client, make_user, make_organization, make_membership, make_product, login_as
):
    from app.ai.providers import get_default_image_provider
    from app.main import app
    from app.services.ai_runs import SANITIZED_ERROR_CATEGORIES, describe_error_category

    owner, org, product = _setup(make_user, make_organization, make_membership, make_product)
    provider = _UnsafeMessageImageProvider()
    app.dependency_overrides[get_default_image_provider] = lambda: provider
    try:
        response = login_as(owner).post(
            _generate_url(org.id, product.id), json={"prompt": "studio photo", "variations": 2}
        )
    finally:
        del app.dependency_overrides[get_default_image_provider]

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"

    for variation in body["variations"]:
        assert variation["error_category"] in SANITIZED_ERROR_CATEGORIES
        # The message is exactly the fixed, category-derived sentence -- not
        # the provider's own text -- regardless of what the provider said.
        assert variation["error_message"] == describe_error_category(variation["error_category"])
        assert "sk-live" not in variation["error_message"]
        assert "api_key" not in variation["error_message"]
        assert "internal-host" not in variation["error_message"]
