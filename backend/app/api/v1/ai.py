from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DBSession

from app.agents.runner import (
    run_product_content_workflow,
    run_product_image_regeneration,
    run_product_image_workflow,
)
from app.ai.providers import get_default_ai_provider, get_default_image_provider
from app.ai.providers.base import AIProvider
from app.api.deps import require_member
from app.api.http_utils import client_ip
from app.db.session import get_db
from app.models import OrganizationMember
from app.schemas.ai import (
    AIRunRead,
    GenerateDescriptionResponse,
    GenerateImageRequest,
    GenerateImageResponse,
    GenerateImageVariationResult,
)
from app.schemas.product import ProductAssetRead, ProductRead
from app.services import ai_runs as ai_run_service
from app.services import product_assets as asset_service
from app.services import products as product_service
from app.services.audit import record_event
from app.services.storage import StorageService, get_storage_service

router = APIRouter(prefix="/organizations/{org_id}/products/{product_id}/ai", tags=["ai"])


def _build_variation_results(
    outcomes: list, assets_by_id: dict[uuid.UUID, ProductAssetRead]
) -> list[GenerateImageVariationResult]:
    # Shared by generate-image and regenerate: both hand back the runner's
    # own VariationOutcome list (app.agents.runner) and just need it turned
    # into wire-shaped results with the asset object swapped in and a
    # human-readable message derived from the sanitized category.
    return [
        GenerateImageVariationResult(
            index=outcome.index,
            status=outcome.status,
            asset=assets_by_id.get(outcome.asset_id) if outcome.asset_id else None,
            error_category=outcome.error_category,
            error_message=ai_run_service.describe_error_category(outcome.error_category),
        )
        for outcome in outcomes
    ]


@router.post("/generate-description", response_model=GenerateDescriptionResponse)
def generate_description(
    product_id: uuid.UUID,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_member)],
    db: Annotated[DBSession, Depends(get_db)],
    provider: Annotated[AIProvider, Depends(get_default_ai_provider)],
) -> GenerateDescriptionResponse:
    try:
        product = product_service.get_product(db, membership.organization_id, product_id)
    except product_service.ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.") from exc

    result = run_product_content_workflow(
        db, membership.organization_id, product, provider=provider, user_id=membership.user_id
    )

    runs = [ai_run_service.get_run(db, membership.organization_id, run_id) for run_id in result.ai_run_ids]

    record_event(
        db,
        "product_ai_content_generated" if result.status == "succeeded" else "product_ai_content_failed",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="product",
        target_id=product.id,
        metadata={"workflow_id": str(result.workflow_id), "error_category": result.error_category},
        ip_address=client_ip(request),
    )

    return GenerateDescriptionResponse(
        workflow_id=result.workflow_id,
        status=result.status,
        analysis=result.analysis,
        generated_description=result.generated_description,
        generated_title=result.generated_title,
        generated_tags=result.generated_tags,
        error_category=result.error_category,
        ai_runs=[AIRunRead.from_run(r) for r in runs],
    )


@router.post("/generate-image", response_model=GenerateImageResponse)
def generate_image(
    product_id: uuid.UUID,
    payload: GenerateImageRequest,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_member)],
    db: Annotated[DBSession, Depends(get_db)],
    text_provider: Annotated[AIProvider, Depends(get_default_ai_provider)],
    image_provider: Annotated[AIProvider, Depends(get_default_image_provider)],
    storage: Annotated[StorageService, Depends(get_storage_service)],
) -> GenerateImageResponse:
    try:
        product = product_service.get_product(db, membership.organization_id, product_id)
    except product_service.ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.") from exc

    result = run_product_image_workflow(
        db,
        membership.organization_id,
        product,
        user_prompt=payload.prompt,
        text_provider=text_provider,
        image_provider=image_provider,
        storage=storage,
        user_id=membership.user_id,
        variations=payload.variations,
    )

    runs = [ai_run_service.get_run(db, membership.organization_id, run_id) for run_id in result.ai_run_ids]
    assets = [
        asset_service.get_asset(db, membership.organization_id, product_id, asset_id)
        for asset_id in result.product_asset_ids
    ]
    assets_by_id = {a.id: ProductAssetRead.from_asset(a) for a in assets}
    failed_categories = [v.error_category for v in result.variations if v.status == "failed"]

    record_event(
        db,
        "product_ai_image_generated" if result.status == "succeeded" else "product_ai_image_failed",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="product",
        target_id=product.id,
        metadata={
            "workflow_id": str(result.workflow_id),
            "error_category": result.error_category,
            "variations_requested": payload.variations,
            "variations_succeeded": len(assets),
            "variations_failed_categories": failed_categories,
        },
        ip_address=client_ip(request),
    )

    return GenerateImageResponse(
        workflow_id=result.workflow_id,
        status=result.status,
        image_prompt=result.image_prompt,
        error_category=result.error_category,
        ai_runs=[AIRunRead.from_run(r) for r in runs],
        asset=ProductAssetRead.from_asset(assets[0]) if assets else None,
        assets=[ProductAssetRead.from_asset(a) for a in assets],
        variations=_build_variation_results(result.variations, assets_by_id),
    )


@router.post("/assets/{asset_id}/regenerate", response_model=GenerateImageResponse)
def regenerate_image(
    product_id: uuid.UUID,
    asset_id: uuid.UUID,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_member)],
    db: Annotated[DBSession, Depends(get_db)],
    image_provider: Annotated[AIProvider, Depends(get_default_image_provider)],
    storage: Annotated[StorageService, Depends(get_storage_service)],
) -> GenerateImageResponse:
    try:
        product = product_service.get_product(db, membership.organization_id, product_id)
    except product_service.ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.") from exc

    try:
        source_asset = asset_service.get_asset(db, membership.organization_id, product_id, asset_id)
    except asset_service.AssetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found.") from exc

    if source_asset.source != "ai_generated":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Only AI-generated images can be regenerated."
        )
    image_prompt = source_asset.ai_run.metadata_.get("image_prompt") if source_asset.ai_run else None
    if not image_prompt:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="No prompt is available to regenerate this image from."
        )

    result = run_product_image_regeneration(
        db,
        membership.organization_id,
        product,
        image_prompt=image_prompt,
        image_provider=image_provider,
        storage=storage,
        user_id=membership.user_id,
        derived_from_asset_id=source_asset.id,
    )

    runs = [ai_run_service.get_run(db, membership.organization_id, run_id) for run_id in result.ai_run_ids]
    new_asset = (
        asset_service.get_asset(db, membership.organization_id, product_id, result.product_asset_id)
        if result.product_asset_id
        else None
    )
    assets_by_id = {new_asset.id: ProductAssetRead.from_asset(new_asset)} if new_asset else {}

    record_event(
        db,
        "product_ai_image_regenerated" if result.status == "succeeded" else "product_ai_image_failed",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="product",
        target_id=product.id,
        metadata={
            "workflow_id": str(result.workflow_id),
            "error_category": result.error_category,
            "regenerated_from_asset_id": str(source_asset.id),
        },
        ip_address=client_ip(request),
    )

    return GenerateImageResponse(
        workflow_id=result.workflow_id,
        status=result.status,
        image_prompt=result.image_prompt,
        error_category=result.error_category,
        ai_runs=[AIRunRead.from_run(r) for r in runs],
        asset=ProductAssetRead.from_asset(new_asset) if new_asset else None,
        assets=[ProductAssetRead.from_asset(new_asset)] if new_asset else [],
        variations=_build_variation_results(result.variations, assets_by_id),
    )


@router.get("/runs", response_model=list[AIRunRead])
def list_ai_runs(
    product_id: uuid.UUID,
    membership: Annotated[OrganizationMember, Depends(require_member)],
    db: Annotated[DBSession, Depends(get_db)],
) -> list[AIRunRead]:
    try:
        product_service.get_product(db, membership.organization_id, product_id)
    except product_service.ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.") from exc

    runs = ai_run_service.list_runs_for_entity(db, membership.organization_id, "product", product_id)
    return [AIRunRead.from_run(r) for r in runs]


@router.post("/runs/{run_id}/apply-description", response_model=ProductRead)
def apply_description(
    product_id: uuid.UUID,
    run_id: uuid.UUID,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_member)],
    db: Annotated[DBSession, Depends(get_db)],
) -> ProductRead:
    try:
        product = product_service.get_product(db, membership.organization_id, product_id)
    except product_service.ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.") from exc

    try:
        run = ai_run_service.get_run(db, membership.organization_id, run_id)
    except ai_run_service.AIRunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI run not found.") from exc

    # Belt-and-suspenders beyond the org_scoped lookup above: the run must
    # also belong to *this* product, not just this organization -- otherwise
    # a valid run_id for a sibling product in the same org could be applied
    # to the wrong product.
    if run.related_entity_type != "product" or run.related_entity_id != product.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI run not found for this product.")

    description = run.metadata_.get("description") if run.status == "succeeded" else None
    if run.run_type != "product_content.generate_description" or not description:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This AI run has no applicable description."
        )

    updated = product_service.update_product(db, product, {"description": description})
    db.commit()
    db.refresh(updated)

    record_event(
        db,
        "product_ai_content_applied",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="product",
        target_id=updated.id,
        metadata={"ai_run_id": str(run.id), "field": "description"},
        ip_address=client_ip(request),
    )

    return ProductRead.from_product(updated)


@router.post("/runs/{run_id}/apply-title", response_model=ProductRead)
def apply_title(
    product_id: uuid.UUID,
    run_id: uuid.UUID,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_member)],
    db: Annotated[DBSession, Depends(get_db)],
) -> ProductRead:
    try:
        product = product_service.get_product(db, membership.organization_id, product_id)
    except product_service.ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.") from exc

    try:
        run = ai_run_service.get_run(db, membership.organization_id, run_id)
    except ai_run_service.AIRunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI run not found.") from exc

    if run.related_entity_type != "product" or run.related_entity_id != product.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI run not found for this product.")

    title = run.metadata_.get("title") if run.status == "succeeded" else None
    if run.run_type != "product_content.generate_title" or not title:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This AI run has no applicable title.")

    updated = product_service.update_product(db, product, {"title": title})
    db.commit()
    db.refresh(updated)

    record_event(
        db,
        "product_ai_content_applied",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="product",
        target_id=updated.id,
        metadata={"ai_run_id": str(run.id), "field": "title"},
        ip_address=client_ip(request),
    )

    return ProductRead.from_product(updated)


@router.post("/runs/{run_id}/apply-tags", response_model=ProductRead)
def apply_tags(
    product_id: uuid.UUID,
    run_id: uuid.UUID,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_member)],
    db: Annotated[DBSession, Depends(get_db)],
) -> ProductRead:
    try:
        product = product_service.get_product(db, membership.organization_id, product_id)
    except product_service.ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.") from exc

    try:
        run = ai_run_service.get_run(db, membership.organization_id, run_id)
    except ai_run_service.AIRunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI run not found.") from exc

    if run.related_entity_type != "product" or run.related_entity_id != product.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI run not found for this product.")

    tags = run.metadata_.get("tags") if run.status == "succeeded" else None
    if run.run_type != "product_content.generate_tags" or not tags:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This AI run has no applicable tags.")

    # Tags live inside the existing metadata_ JSONB blob -- there's no
    # dedicated Product.tags column, so this merges into whatever metadata
    # already exists rather than replacing it wholesale.
    updated = product_service.update_product(db, product, {"metadata": {**product.metadata_, "tags": tags}})
    db.commit()
    db.refresh(updated)

    record_event(
        db,
        "product_ai_content_applied",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="product",
        target_id=updated.id,
        metadata={"ai_run_id": str(run.id), "field": "tags"},
        ip_address=client_ip(request),
    )

    return ProductRead.from_product(updated)
