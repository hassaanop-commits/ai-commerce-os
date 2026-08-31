from __future__ import annotations

from decimal import Decimal

from app.ai.providers.base import ImageResult
from app.ai.providers.mock_provider import MockProvider
from app.ai.tools import product_images as tools
from app.ai.tools._common import ToolExecutionError
from app.models import AIRun, ProductAsset


class _GarbageImageProvider:
    """A provider that returns bytes which don't sniff as any real image
    format -- exercises the byte-validation path independently of the mock
    provider's own (always-valid) output."""

    name = "garbage"

    def generate_image(self, *, prompt: str, model: str, size: str = "1024x1024") -> ImageResult:
        return ImageResult(content=b"not a real image, just plain text padding" * 4, content_type="image/png", model=model)


def _asset_count(db, product_id) -> int:
    return db.query(ProductAsset).filter(ProductAsset.product_id == product_id).count()


def test_generate_product_image_creates_pending_review_asset(db, make_organization, make_product, storage_service):
    org = make_organization()
    product = make_product(org, title="Red Mug")
    provider = MockProvider()

    run_id, asset = tools.generate_product_image(
        db, org.id, product, provider=provider, model="mock-image-model", image_prompt="a red mug", storage=storage_service
    )

    assert asset.source == "ai_generated"
    assert asset.approval_status == "pending_review"
    assert asset.is_primary is False
    assert asset.status == "ready"
    assert asset.ai_run_id == run_id
    assert asset.derived_from_asset_id is None

    run = db.get(AIRun, run_id)
    assert run.status == "succeeded"
    assert run.run_type == "product_image.generate"
    assert run.input_tokens == 0
    assert run.output_tokens == 0
    assert run.cost_usd == Decimal("0")


def test_generate_product_image_failure_creates_zero_assets(db, make_organization, make_product, storage_service):
    org = make_organization()
    product = make_product(org)
    provider = MockProvider()

    try:
        tools.generate_product_image(
            db,
            org.id,
            product,
            provider=provider,
            model="mock-image-model",
            image_prompt="please __fail__ this",
            storage=storage_service,
        )
        assert False, "expected ToolExecutionError"
    except ToolExecutionError as exc:
        assert exc.category == "provider_error"
        run = db.get(AIRun, exc.run_id)
        assert run.status == "failed"
        assert run.error_message == "provider_error"

    assert _asset_count(db, product.id) == 0


def test_generate_product_image_rejects_invalid_bytes(db, make_organization, make_product, storage_service):
    org = make_organization()
    product = make_product(org)
    provider = _GarbageImageProvider()

    try:
        tools.generate_product_image(
            db, org.id, product, provider=provider, model="garbage-model", image_prompt="a red mug", storage=storage_service
        )
        assert False, "expected ToolExecutionError"
    except ToolExecutionError as exc:
        assert exc.category == "invalid_response"
        run = db.get(AIRun, exc.run_id)
        assert run.status == "failed"
        assert run.error_message == "invalid_response"

    assert _asset_count(db, product.id) == 0


def test_generate_image_prompt_returns_text(db, make_organization, make_product):
    org = make_organization()
    product = make_product(org, title="Red Mug")
    provider = MockProvider()

    run_id, image_prompt = tools.generate_image_prompt(
        db, org.id, product, provider=provider, model="mock-model", user_prompt="studio photo, white background"
    )

    assert "studio photo" in image_prompt
    run = db.get(AIRun, run_id)
    assert run.run_type == "product_image.craft_prompt"
    assert run.status == "succeeded"
