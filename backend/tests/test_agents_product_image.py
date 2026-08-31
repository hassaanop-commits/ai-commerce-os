from __future__ import annotations

from app.agents.runner import run_product_image_workflow
from app.ai.providers.mock_provider import MockProvider
from app.models import AIRun, ProductAsset


def test_image_workflow_succeeds_and_correlates_runs(db, make_organization, make_product, storage_service):
    org = make_organization()
    product = make_product(org, title="Red Mug")
    text_provider = MockProvider()
    image_provider = MockProvider()

    result = run_product_image_workflow(
        db,
        org.id,
        product,
        user_prompt="studio photo, white background",
        text_provider=text_provider,
        image_provider=image_provider,
        storage=storage_service,
        user_id=None,
    )

    assert result.status == "succeeded"
    assert result.image_prompt is not None
    assert result.product_asset_id is not None
    assert len(result.ai_run_ids) == 2

    runs = db.query(AIRun).filter(AIRun.id.in_(result.ai_run_ids)).all()
    assert len(runs) == 2
    assert {r.run_type for r in runs} == {"product_image.craft_prompt", "product_image.generate"}
    assert all(r.status == "succeeded" for r in runs)
    workflow_ids = {r.metadata_["workflow_id"] for r in runs}
    assert workflow_ids == {str(result.workflow_id)}

    asset = db.get(ProductAsset, result.product_asset_id)
    assert asset.approval_status == "pending_review"
    assert asset.is_primary is False


def test_image_workflow_short_circuits_when_craft_prompt_fails(db, make_organization, make_product, storage_service):
    org = make_organization()
    product = make_product(org)
    text_provider = MockProvider()
    image_provider = MockProvider()

    result = run_product_image_workflow(
        db,
        org.id,
        product,
        user_prompt="please __fail__ this",
        text_provider=text_provider,
        image_provider=image_provider,
        storage=storage_service,
        user_id=None,
    )

    assert result.status == "failed"
    assert result.error_category == "provider_error"
    assert result.product_asset_id is None
    assert len(result.ai_run_ids) == 1

    run = db.get(AIRun, result.ai_run_ids[0])
    assert run.run_type == "product_image.craft_prompt"
    assert run.status == "failed"

    assert db.query(ProductAsset).filter(ProductAsset.product_id == product.id).count() == 0
