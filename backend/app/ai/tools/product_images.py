from __future__ import annotations

import uuid

from sqlalchemy.orm import Session as DBSession

from app.ai.pricing import estimate_image_cost_usd
from app.ai.providers.base import AIProvider
from app.ai.tools._common import ToolExecutionError, run_text_completion, start_and_call
from app.models import Product, ProductAsset
from app.services import ai_runs
from app.services import product_assets as asset_service
from app.services.storage import StorageService, generate_storage_key
from app.services.uploads import InvalidUploadError, extension_for_content_type, validate_image_upload

DEFAULT_IMAGE_SIZE = "1024x1024"

# process_product_asset (derived-image editing: background removal, upscale,
# etc.) is explicitly out of scope for this phase -- interface only.


def generate_image_prompt(
    db: DBSession,
    organization_id: uuid.UUID,
    product: Product,
    *,
    provider: AIProvider,
    model: str,
    user_prompt: str,
    user_id: uuid.UUID | None = None,
    workflow_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, str]:
    system = (
        "You are a product photography director for an e-commerce platform. "
        "Turn the product details and the requester's description into a single, "
        "concrete image-generation prompt (1-2 sentences) for a clean, professional "
        "product photo. Do not add text, logos, or watermarks to the scene."
    )
    prompt = (
        f"Product: {product.title}\n"
        f"Existing description: {product.description or '(none)'}\n"
        f"Requested image: {user_prompt}"
    )
    return run_text_completion(
        db,
        organization_id,
        run_type="product_image.craft_prompt",
        provider=provider,
        model=model,
        user_id=user_id,
        related_entity_type="product",
        related_entity_id=product.id,
        workflow_id=workflow_id,
        system=system,
        prompt=prompt,
        output_key="image_prompt",
    )


def generate_product_image(
    db: DBSession,
    organization_id: uuid.UUID,
    product: Product,
    *,
    provider: AIProvider,
    model: str,
    image_prompt: str,
    storage: StorageService,
    user_id: uuid.UUID | None = None,
    workflow_id: uuid.UUID | None = None,
    size: str = DEFAULT_IMAGE_SIZE,
    derived_from_asset_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, ProductAsset]:
    run, result = start_and_call(
        db,
        organization_id,
        run_type="product_image.generate",
        provider=provider,
        model=model,
        user_id=user_id,
        related_entity_type="product",
        related_entity_id=product.id,
        workflow_id=workflow_id,
        call=lambda: provider.generate_image(prompt=image_prompt, model=model, size=size),
    )

    # Never trust the provider's declared content type -- sniff the actual
    # bytes exactly like a browser upload is validated (app.services.uploads),
    # and only mark the run succeeded once that's confirmed. A run that fails
    # this check never produces a ProductAsset row.
    try:
        content_type = validate_image_upload(result.content)
    except InvalidUploadError as exc:
        ai_runs.fail_run(db, run, category="invalid_response", detail=str(exc))
        db.commit()
        raise ToolExecutionError(run.id, "invalid_response") from exc

    storage_key = generate_storage_key(organization_id, product.id, extension_for_content_type(content_type))
    storage.upload(storage_key, result.content, content_type)

    cost = estimate_image_cost_usd(provider.name, result.model, size)
    # image_prompt is duplicated onto the *generate* run (craft_prompt already
    # stores it under the same key) so a single asset's originating prompt is
    # always readable from asset.ai_run alone -- callers never need to
    # cross-reference a sibling run by workflow_id just to show/reuse it
    # (see ProductAssetRead.from_asset and the /regenerate endpoint).
    ai_runs.complete_run(
        db,
        run,
        input_tokens=0,
        output_tokens=0,
        cost_usd=cost,
        output_metadata={"size": size, "image_prompt": image_prompt},
    )
    db.commit()

    asset = asset_service.create_generated_asset(
        db,
        product,
        storage_key=storage_key,
        content_type=content_type,
        ai_run_id=run.id,
        derived_from_asset_id=derived_from_asset_id,
    )
    db.commit()

    return run.id, asset


def process_product_asset(*args, **kwargs):
    raise NotImplementedError("Asset processing is not implemented yet (planned for a later phase).")
