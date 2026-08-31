from __future__ import annotations

import uuid

from sqlalchemy.orm import Session as DBSession

from app.db.tenant import org_scoped
from app.models import Product, ProductAsset
from app.services.storage import StorageService


class AssetNotFoundError(Exception):
    pass


class AssetNotApprovedError(Exception):
    """Raised when trying to set is_primary on an asset that isn't
    'approved' or 'not_required' -- mirrors the DB-level CHECK constraint
    (ck_product_assets_primary_requires_approval) so callers get a clean
    exception instead of relying on the constraint violation alone."""

    pass


class InvalidApprovalTransitionError(Exception):
    """Raised when approving/rejecting an asset that isn't currently
    'pending_review' -- approval is a one-way, one-shot transition."""

    pass


def _next_position(db: DBSession, product_id: uuid.UUID) -> int:
    current_max = (
        db.query(ProductAsset.position)
        .filter(ProductAsset.product_id == product_id)
        .order_by(ProductAsset.position.desc())
        .limit(1)
        .scalar()
    )
    return (current_max or 0) + 1


def _clear_existing_primary(db: DBSession, product_id: uuid.UUID) -> None:
    db.query(ProductAsset).filter(
        ProductAsset.product_id == product_id, ProductAsset.is_primary.is_(True)
    ).update({"is_primary": False})


def create_uploaded_asset(
    db: DBSession,
    product: Product,
    *,
    storage_key: str,
    content_type: str,
    is_primary: bool = False,
) -> ProductAsset:
    if is_primary:
        _clear_existing_primary(db, product.id)

    asset_id = uuid.uuid4()
    # The service owns the URL convention (an authenticated route, since
    # local storage has no secure public URL of its own -- see
    # LocalStorageProvider.get_url) so callers never need to know it.
    url = f"/api/v1/organizations/{product.organization_id}/products/{product.id}/assets/{asset_id}/file"

    asset = ProductAsset(
        id=asset_id,
        organization_id=product.organization_id,
        product_id=product.id,
        source="upload",
        asset_type="image",
        storage_key=storage_key,
        url=url,
        status="ready",
        position=_next_position(db, product.id),
        is_primary=is_primary,
        metadata_={"content_type": content_type},
    )
    db.add(asset)
    db.flush()
    return asset


def create_generated_asset(
    db: DBSession,
    product: Product,
    *,
    storage_key: str,
    content_type: str,
    ai_run_id: uuid.UUID,
    derived_from_asset_id: uuid.UUID | None = None,
) -> ProductAsset:
    # AI-generated assets are always created pending_review, never primary --
    # is_primary isn't even a parameter here, so there's no path that could
    # accidentally publish one straight from generation.
    asset_id = uuid.uuid4()
    url = f"/api/v1/organizations/{product.organization_id}/products/{product.id}/assets/{asset_id}/file"

    asset = ProductAsset(
        id=asset_id,
        organization_id=product.organization_id,
        product_id=product.id,
        source="ai_generated",
        derived_from_asset_id=derived_from_asset_id,
        ai_run_id=ai_run_id,
        asset_type="image",
        storage_key=storage_key,
        url=url,
        status="ready",
        approval_status="pending_review",
        position=_next_position(db, product.id),
        is_primary=False,
        metadata_={"content_type": content_type},
    )
    db.add(asset)
    db.flush()
    return asset


def list_assets(db: DBSession, organization_id: uuid.UUID, product_id: uuid.UUID) -> list[ProductAsset]:
    return (
        db.execute(
            org_scoped(ProductAsset, organization_id)
            .where(ProductAsset.product_id == product_id)
            .order_by(ProductAsset.position)
        )
        .scalars()
        .all()
    )


def get_asset(
    db: DBSession, organization_id: uuid.UUID, product_id: uuid.UUID, asset_id: uuid.UUID
) -> ProductAsset:
    asset = (
        db.execute(
            org_scoped(ProductAsset, organization_id).where(
                ProductAsset.id == asset_id, ProductAsset.product_id == product_id
            )
        )
        .scalars()
        .one_or_none()
    )
    if asset is None:
        raise AssetNotFoundError(asset_id)
    return asset


def update_asset(
    db: DBSession,
    asset: ProductAsset,
    *,
    is_primary: bool | None = None,
    position: int | None = None,
) -> ProductAsset:
    if is_primary is True and not asset.is_primary:
        if asset.approval_status not in ("approved", "not_required"):
            raise AssetNotApprovedError(asset.id)
        _clear_existing_primary(db, asset.product_id)
        asset.is_primary = True
    elif is_primary is False:
        asset.is_primary = False

    if position is not None:
        asset.position = position

    db.flush()
    return asset


def approve_asset(db: DBSession, asset: ProductAsset) -> ProductAsset:
    if asset.approval_status != "pending_review":
        raise InvalidApprovalTransitionError(asset.id)
    asset.approval_status = "approved"
    db.flush()
    return asset


def reject_asset(db: DBSession, asset: ProductAsset) -> ProductAsset:
    if asset.approval_status != "pending_review":
        raise InvalidApprovalTransitionError(asset.id)
    # Rejecting only changes approval_status -- the row (and its stored
    # file) stays put. Deletion is a separate, explicit action via the
    # existing DELETE endpoint, unchanged by this.
    asset.approval_status = "rejected"
    db.flush()
    return asset


def delete_asset(db: DBSession, storage: StorageService, asset: ProductAsset) -> None:
    was_primary = asset.is_primary
    product_id = asset.product_id
    storage_key = asset.storage_key

    db.delete(asset)
    db.flush()
    storage.delete(storage_key)

    if was_primary:
        # Only an approval-eligible asset may be promoted -- otherwise this
        # would violate ck_product_assets_primary_requires_approval by
        # silently making a pending-review or rejected asset primary.
        next_asset = (
            db.query(ProductAsset)
            .filter(
                ProductAsset.product_id == product_id,
                ProductAsset.approval_status.in_(("approved", "not_required")),
            )
            .order_by(ProductAsset.position)
            .first()
        )
        if next_asset is not None:
            next_asset.is_primary = True
            db.flush()
