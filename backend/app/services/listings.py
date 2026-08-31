from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm import joinedload

from app.db.tenant import org_scoped
from app.marketplaces.adapters import MarketplaceError, get_marketplace_adapter
from app.marketplaces.adapters.base import ListingPayload
from app.models import Listing, MarketplaceConnection, Product

# The only error categories ever persisted to listings.last_error -- kept
# closed and separate from any adapter's own exception text, same discipline
# as app.services.ai_runs.SANITIZED_ERROR_CATEGORIES.
SANITIZED_MARKETPLACE_ERROR_CATEGORIES = frozenset(
    {
        "connection_not_configured",
        "connection_expired",
        "rate_limited",
        "validation_rejected",
        "marketplace_error",
        "invalid_response",
        "unknown_error",
    }
)


class ListingNotFoundError(Exception):
    pass


class NoApprovedPrimaryAssetError(Exception):
    pass


class ConnectionNotConnectedError(Exception):
    pass


class InvalidListingTransitionError(Exception):
    pass


def create_draft(
    db: DBSession,
    organization_id: uuid.UUID,
    product: Product,
    connection: MarketplaceConnection,
) -> Listing:
    if connection.status != "connected":
        raise ConnectionNotConnectedError(connection.id)

    primary_asset = next((a for a in product.assets if a.is_primary), None)
    if primary_asset is None:
        raise NoApprovedPrimaryAssetError(product.id)
    # is_primary can only ever be true on an asset whose approval_status is
    # 'approved' or 'not_required' -- enforced by
    # ck_product_assets_primary_requires_approval (Phase I). Finding a
    # primary asset at all is therefore sufficient; there's nothing further
    # to check here.

    listing = Listing(
        organization_id=organization_id,
        product_id=product.id,
        marketplace_connection_id=connection.id,
        title=product.title,
        description=product.description or "",
        price=product.price,
        currency=product.currency,
        listing_data={"image_url": primary_asset.url},
        status="draft",
    )
    db.add(listing)
    db.flush()
    return listing


def list_listings_for_product(
    db: DBSession, organization_id: uuid.UUID, product_id: uuid.UUID
) -> list[Listing]:
    return (
        db.execute(
            org_scoped(Listing, organization_id)
            .options(joinedload(Listing.marketplace_connection).joinedload(MarketplaceConnection.marketplace))
            .where(Listing.product_id == product_id)
            .order_by(Listing.created_at.desc())
        )
        .scalars()
        .all()
    )


def get_listing(
    db: DBSession, organization_id: uuid.UUID, product_id: uuid.UUID, listing_id: uuid.UUID
) -> Listing:
    listing = (
        db.execute(
            org_scoped(Listing, organization_id)
            .options(joinedload(Listing.marketplace_connection).joinedload(MarketplaceConnection.marketplace))
            .where(Listing.id == listing_id, Listing.product_id == product_id)
        )
        .scalars()
        .one_or_none()
    )
    if listing is None:
        raise ListingNotFoundError(listing_id)
    return listing


def approve_listing(db: DBSession, listing: Listing) -> Listing:
    if listing.status != "draft":
        raise InvalidListingTransitionError(listing.id)
    listing.status = "approved"
    db.flush()
    return listing


def delete_draft(db: DBSession, listing: Listing) -> None:
    if listing.status != "draft":
        raise InvalidListingTransitionError(listing.id)
    db.delete(listing)
    db.flush()


def _attempt_publish(db: DBSession, listing: Listing) -> Listing:
    # Unlike the simple state setters above, publish/retry/end each make an
    # external adapter call, so each commits its own transition durably
    # (same reasoning as app.ai.tools._common.start_and_call): the
    # 'publishing' state, and any resulting 'error', must survive
    # independently of whatever the caller does next.
    connection = listing.marketplace_connection
    if connection.status != "connected":
        raise ConnectionNotConnectedError(connection.id)

    listing.status = "publishing"
    db.flush()
    db.commit()

    payload = ListingPayload(
        title=listing.title,
        description=listing.description or "",
        price=listing.price,
        currency=listing.currency,
        image_url=listing.listing_data.get("image_url"),
    )
    adapter = get_marketplace_adapter(connection.marketplace.key)

    try:
        result = adapter.create_listing(connection=connection, payload=payload)
    except MarketplaceError as exc:
        safe_category = (
            exc.category if exc.category in SANITIZED_MARKETPLACE_ERROR_CATEGORIES else "unknown_error"
        )
        listing.status = "error"
        listing.last_error = safe_category
        db.flush()
        db.commit()
        raise

    listing.status = "active"
    listing.external_listing_id = result.external_listing_id
    listing.last_synced_at = datetime.now(timezone.utc)
    listing.last_error = None
    if result.marketplace_url:
        listing.listing_data = {**listing.listing_data, "marketplace_url": result.marketplace_url}
    db.flush()
    db.commit()
    return listing


def publish_listing(db: DBSession, listing: Listing) -> Listing:
    if listing.status != "approved":
        raise InvalidListingTransitionError(listing.id)
    return _attempt_publish(db, listing)


def retry_listing(db: DBSession, listing: Listing) -> Listing:
    if listing.status != "error":
        raise InvalidListingTransitionError(listing.id)
    return _attempt_publish(db, listing)


def end_listing(db: DBSession, listing: Listing) -> Listing:
    if listing.status != "active":
        raise InvalidListingTransitionError(listing.id)

    connection = listing.marketplace_connection
    adapter = get_marketplace_adapter(connection.marketplace.key)

    try:
        adapter.end_listing(connection=connection, external_listing_id=listing.external_listing_id)
    except MarketplaceError as exc:
        safe_category = (
            exc.category if exc.category in SANITIZED_MARKETPLACE_ERROR_CATEGORIES else "unknown_error"
        )
        listing.last_error = safe_category
        db.flush()
        db.commit()
        raise

    listing.status = "ended"
    listing.last_error = None
    db.flush()
    db.commit()
    return listing
