from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DBSession

from app.api.deps import require_admin, require_member
from app.api.http_utils import client_ip
from app.db.session import get_db
from app.marketplaces.adapters import MarketplaceError
from app.models import OrganizationMember
from app.schemas.marketplace import ListingCreateRequest, ListingRead
from app.services import listings as listing_service
from app.services import marketplace_connections as connection_service
from app.services import products as product_service
from app.services.audit import record_event

router = APIRouter(prefix="/organizations/{org_id}/products/{product_id}/listings", tags=["listings"])


def _get_owned_listing(db: DBSession, organization_id: uuid.UUID, product_id: uuid.UUID, listing_id: uuid.UUID):
    try:
        return listing_service.get_listing(db, organization_id, product_id, listing_id)
    except listing_service.ListingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found.") from exc


@router.get("", response_model=list[ListingRead])
def list_listings(
    product_id: uuid.UUID,
    membership: Annotated[OrganizationMember, Depends(require_member)],
    db: Annotated[DBSession, Depends(get_db)],
) -> list[ListingRead]:
    listings = listing_service.list_listings_for_product(db, membership.organization_id, product_id)
    return [ListingRead.from_listing(listing) for listing in listings]


@router.post("", response_model=ListingRead, status_code=status.HTTP_201_CREATED)
def create_listing(
    product_id: uuid.UUID,
    payload: ListingCreateRequest,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_member)],
    db: Annotated[DBSession, Depends(get_db)],
) -> ListingRead:
    try:
        product = product_service.get_product(db, membership.organization_id, product_id)
    except product_service.ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.") from exc

    try:
        connection = connection_service.get_connection(
            db, membership.organization_id, payload.marketplace_connection_id
        )
    except connection_service.MarketplaceConnectionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Marketplace connection not found."
        ) from exc

    try:
        listing = listing_service.create_draft(db, membership.organization_id, product, connection)
    except listing_service.NoApprovedPrimaryAssetError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This product needs an approved primary image before a listing can be created.",
        ) from exc
    except listing_service.ConnectionNotConnectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This marketplace connection is not connected."
        ) from exc

    db.commit()
    db.refresh(listing)

    record_event(
        db,
        "listing_created",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="listing",
        target_id=listing.id,
        metadata={"product_id": str(product_id)},
        ip_address=client_ip(request),
    )

    return ListingRead.from_listing(listing)


@router.post("/{listing_id}/approve", response_model=ListingRead)
def approve_listing(
    product_id: uuid.UUID,
    listing_id: uuid.UUID,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_member)],
    db: Annotated[DBSession, Depends(get_db)],
) -> ListingRead:
    listing = _get_owned_listing(db, membership.organization_id, product_id, listing_id)

    try:
        updated = listing_service.approve_listing(db, listing)
    except listing_service.InvalidListingTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This listing is not a draft.") from exc

    db.commit()
    db.refresh(updated)

    record_event(
        db,
        "listing_approved",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="listing",
        target_id=updated.id,
        ip_address=client_ip(request),
    )

    return ListingRead.from_listing(updated)


@router.delete("/{listing_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_listing_draft(
    product_id: uuid.UUID,
    listing_id: uuid.UUID,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_member)],
    db: Annotated[DBSession, Depends(get_db)],
) -> None:
    listing = _get_owned_listing(db, membership.organization_id, product_id, listing_id)

    try:
        listing_service.delete_draft(db, listing)
    except listing_service.InvalidListingTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Only draft listings can be deleted."
        ) from exc

    listing_id_for_audit = listing.id
    db.commit()

    record_event(
        db,
        "listing_deleted",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="listing",
        target_id=listing_id_for_audit,
        ip_address=client_ip(request),
    )


@router.post("/{listing_id}/publish", response_model=ListingRead)
def publish_listing(
    product_id: uuid.UUID,
    listing_id: uuid.UUID,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_admin)],
    db: Annotated[DBSession, Depends(get_db)],
) -> ListingRead:
    listing = _get_owned_listing(db, membership.organization_id, product_id, listing_id)

    try:
        updated = listing_service.publish_listing(db, listing)
    except listing_service.InvalidListingTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This listing is not approved.") from exc
    except listing_service.ConnectionNotConnectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This marketplace connection is not connected."
        ) from exc
    except MarketplaceError as exc:
        # listing_service already committed the 'error' state -- nothing
        # left to commit here, only to audit and report it back.
        record_event(
            db,
            "listing_publish_failed",
            actor_user_id=membership.user_id,
            organization_id=membership.organization_id,
            target_type="listing",
            target_id=listing.id,
            metadata={"error_category": exc.category},
            ip_address=client_ip(request),
        )
        return ListingRead.from_listing(listing)

    record_event(
        db,
        "listing_published",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="listing",
        target_id=updated.id,
        metadata={"external_listing_id": updated.external_listing_id},
        ip_address=client_ip(request),
    )

    return ListingRead.from_listing(updated)


@router.post("/{listing_id}/retry", response_model=ListingRead)
def retry_listing(
    product_id: uuid.UUID,
    listing_id: uuid.UUID,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_admin)],
    db: Annotated[DBSession, Depends(get_db)],
) -> ListingRead:
    listing = _get_owned_listing(db, membership.organization_id, product_id, listing_id)

    try:
        updated = listing_service.retry_listing(db, listing)
    except listing_service.InvalidListingTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This listing is not in an error state."
        ) from exc
    except listing_service.ConnectionNotConnectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This marketplace connection is not connected."
        ) from exc
    except MarketplaceError as exc:
        record_event(
            db,
            "listing_publish_failed",
            actor_user_id=membership.user_id,
            organization_id=membership.organization_id,
            target_type="listing",
            target_id=listing.id,
            metadata={"error_category": exc.category, "retry": True},
            ip_address=client_ip(request),
        )
        return ListingRead.from_listing(listing)

    record_event(
        db,
        "listing_published",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="listing",
        target_id=updated.id,
        metadata={"external_listing_id": updated.external_listing_id, "retry": True},
        ip_address=client_ip(request),
    )

    return ListingRead.from_listing(updated)


@router.post("/{listing_id}/end", response_model=ListingRead)
def end_listing(
    product_id: uuid.UUID,
    listing_id: uuid.UUID,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_admin)],
    db: Annotated[DBSession, Depends(get_db)],
) -> ListingRead:
    listing = _get_owned_listing(db, membership.organization_id, product_id, listing_id)

    try:
        updated = listing_service.end_listing(db, listing)
    except listing_service.InvalidListingTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This listing is not active.") from exc
    except MarketplaceError as exc:
        record_event(
            db,
            "listing_publish_failed",
            actor_user_id=membership.user_id,
            organization_id=membership.organization_id,
            target_type="listing",
            target_id=listing.id,
            metadata={"error_category": exc.category, "action": "end"},
            ip_address=client_ip(request),
        )
        return ListingRead.from_listing(listing)

    record_event(
        db,
        "listing_ended",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="listing",
        target_id=updated.id,
        ip_address=client_ip(request),
    )

    return ListingRead.from_listing(updated)
