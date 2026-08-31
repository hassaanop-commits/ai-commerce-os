from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.orm import Session as DBSession

from app.api.deps import require_admin, require_member
from app.api.http_utils import client_ip
from app.db.session import get_db
from app.models import OrganizationMember
from app.schemas.product import (
    ProductAssetRead,
    ProductAssetUpdateRequest,
    ProductCreateRequest,
    ProductRead,
    ProductUpdateRequest,
)
from app.services import product_assets as asset_service
from app.services import products as product_service
from app.services.audit import record_event
from app.services.storage import StorageService, generate_storage_key, get_storage_service
from app.services.uploads import InvalidUploadError, extension_for_content_type, validate_image_upload

router = APIRouter(prefix="/organizations/{org_id}/products", tags=["products"])


@router.get("", response_model=list[ProductRead])
def list_products(
    membership: Annotated[OrganizationMember, Depends(require_member)],
    db: Annotated[DBSession, Depends(get_db)],
) -> list[ProductRead]:
    products = product_service.list_products(db, membership.organization_id)
    return [ProductRead.from_product(p) for p in products]


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreateRequest,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_member)],
    db: Annotated[DBSession, Depends(get_db)],
) -> ProductRead:
    try:
        product = product_service.create_product(
            db,
            membership.organization_id,
            sku=payload.sku,
            title=payload.title,
            description=payload.description,
            price=payload.price,
            currency=payload.currency,
            metadata=payload.metadata,
        )
    except product_service.DuplicateSkuError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A product with this SKU already exists."
        ) from exc

    db.commit()
    db.refresh(product)

    record_event(
        db,
        "product_created",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="product",
        target_id=product.id,
        metadata={"sku": product.sku},
        ip_address=client_ip(request),
    )

    return ProductRead.from_product(product)


@router.get("/{product_id}", response_model=ProductRead)
def get_product(
    product_id: uuid.UUID,
    membership: Annotated[OrganizationMember, Depends(require_member)],
    db: Annotated[DBSession, Depends(get_db)],
) -> ProductRead:
    try:
        product = product_service.get_product(db, membership.organization_id, product_id)
    except product_service.ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.") from exc
    return ProductRead.from_product(product)


@router.patch("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdateRequest,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_member)],
    db: Annotated[DBSession, Depends(get_db)],
) -> ProductRead:
    try:
        product = product_service.get_product(db, membership.organization_id, product_id)
    except product_service.ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.") from exc

    updates = payload.model_dump(exclude_unset=True)
    try:
        updated = product_service.update_product(db, product, updates)
    except product_service.DuplicateSkuError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A product with this SKU already exists."
        ) from exc

    db.commit()
    db.refresh(updated)

    record_event(
        db,
        "product_updated",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="product",
        target_id=updated.id,
        metadata={"fields": sorted(updates.keys())},
        ip_address=client_ip(request),
    )

    return ProductRead.from_product(updated)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_product(
    product_id: uuid.UUID,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_member)],
    db: Annotated[DBSession, Depends(get_db)],
) -> None:
    try:
        product = product_service.get_product(db, membership.organization_id, product_id)
    except product_service.ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.") from exc

    product_service.delete_product(db, product)
    db.commit()

    record_event(
        db,
        "product_deleted",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="product",
        target_id=product_id,
        ip_address=client_ip(request),
    )


# ---- assets -----------------------------------------------------------------


@router.get("/{product_id}/assets", response_model=list[ProductAssetRead])
def list_product_assets(
    product_id: uuid.UUID,
    membership: Annotated[OrganizationMember, Depends(require_member)],
    db: Annotated[DBSession, Depends(get_db)],
) -> list[ProductAssetRead]:
    assets = asset_service.list_assets(db, membership.organization_id, product_id)
    return [ProductAssetRead.from_asset(a) for a in assets]


@router.post(
    "/{product_id}/assets", response_model=ProductAssetRead, status_code=status.HTTP_201_CREATED
)
async def upload_product_asset(
    product_id: uuid.UUID,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_member)],
    db: Annotated[DBSession, Depends(get_db)],
    storage: Annotated[StorageService, Depends(get_storage_service)],
    file: Annotated[UploadFile, File()],
    is_primary: Annotated[bool, Form()] = False,
) -> ProductAssetRead:
    try:
        product = product_service.get_product(db, membership.organization_id, product_id)
    except product_service.ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.") from exc

    content = await file.read()
    try:
        content_type = validate_image_upload(content)
    except InvalidUploadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc

    storage_key = generate_storage_key(
        membership.organization_id, product.id, extension_for_content_type(content_type)
    )
    storage.upload(storage_key, content, content_type)

    try:
        asset = asset_service.create_uploaded_asset(
            db, product, storage_key=storage_key, content_type=content_type, is_primary=is_primary
        )
        db.commit()
    except Exception:
        storage.delete(storage_key)
        raise
    db.refresh(asset)

    record_event(
        db,
        "product_asset_uploaded",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="product_asset",
        target_id=asset.id,
        metadata={"product_id": str(product.id), "content_type": content_type},
        ip_address=client_ip(request),
    )

    return ProductAssetRead.from_asset(asset)


@router.get("/{product_id}/assets/{asset_id}/file")
def get_product_asset_file(
    product_id: uuid.UUID,
    asset_id: uuid.UUID,
    membership: Annotated[OrganizationMember, Depends(require_member)],
    db: Annotated[DBSession, Depends(get_db)],
    storage: Annotated[StorageService, Depends(get_storage_service)],
) -> Response:
    try:
        asset = asset_service.get_asset(db, membership.organization_id, product_id, asset_id)
    except asset_service.AssetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found.") from exc

    try:
        content = storage.read(asset.storage_key)
    except (FileNotFoundError, OSError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset file not found.") from exc

    content_type = asset.metadata_.get("content_type", "application/octet-stream")
    return Response(content=content, media_type=content_type)


@router.patch("/{product_id}/assets/{asset_id}", response_model=ProductAssetRead)
def update_product_asset(
    product_id: uuid.UUID,
    asset_id: uuid.UUID,
    payload: ProductAssetUpdateRequest,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_member)],
    db: Annotated[DBSession, Depends(get_db)],
) -> ProductAssetRead:
    try:
        asset = asset_service.get_asset(db, membership.organization_id, product_id, asset_id)
    except asset_service.AssetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found.") from exc

    try:
        updated = asset_service.update_asset(
            db, asset, is_primary=payload.is_primary, position=payload.position
        )
    except asset_service.AssetNotApprovedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This asset must be approved before it can become the primary image.",
        ) from exc
    db.commit()
    db.refresh(updated)

    record_event(
        db,
        "product_asset_updated",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="product_asset",
        target_id=updated.id,
        ip_address=client_ip(request),
    )

    return ProductAssetRead.from_asset(updated)


@router.delete(
    "/{product_id}/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
def delete_product_asset(
    product_id: uuid.UUID,
    asset_id: uuid.UUID,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_member)],
    db: Annotated[DBSession, Depends(get_db)],
    storage: Annotated[StorageService, Depends(get_storage_service)],
) -> None:
    try:
        asset = asset_service.get_asset(db, membership.organization_id, product_id, asset_id)
    except asset_service.AssetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found.") from exc

    deleted_asset_id = asset.id
    asset_service.delete_asset(db, storage, asset)
    db.commit()

    record_event(
        db,
        "product_asset_deleted",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="product_asset",
        target_id=deleted_asset_id,
        ip_address=client_ip(request),
    )


@router.post("/{product_id}/assets/{asset_id}/approve", response_model=ProductAssetRead)
def approve_product_asset(
    product_id: uuid.UUID,
    asset_id: uuid.UUID,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_admin)],
    db: Annotated[DBSession, Depends(get_db)],
) -> ProductAssetRead:
    try:
        asset = asset_service.get_asset(db, membership.organization_id, product_id, asset_id)
    except asset_service.AssetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found.") from exc

    try:
        updated = asset_service.approve_asset(db, asset)
    except asset_service.InvalidApprovalTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This asset is not pending review."
        ) from exc
    db.commit()
    db.refresh(updated)

    record_event(
        db,
        "product_asset_approved",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="product_asset",
        target_id=updated.id,
        ip_address=client_ip(request),
    )

    return ProductAssetRead.from_asset(updated)


@router.post("/{product_id}/assets/{asset_id}/reject", response_model=ProductAssetRead)
def reject_product_asset(
    product_id: uuid.UUID,
    asset_id: uuid.UUID,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_admin)],
    db: Annotated[DBSession, Depends(get_db)],
) -> ProductAssetRead:
    try:
        asset = asset_service.get_asset(db, membership.organization_id, product_id, asset_id)
    except asset_service.AssetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found.") from exc

    try:
        updated = asset_service.reject_asset(db, asset)
    except asset_service.InvalidApprovalTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This asset is not pending review."
        ) from exc
    db.commit()
    db.refresh(updated)

    record_event(
        db,
        "product_asset_rejected",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="product_asset",
        target_id=updated.id,
        ip_address=client_ip(request),
    )

    return ProductAssetRead.from_asset(updated)
