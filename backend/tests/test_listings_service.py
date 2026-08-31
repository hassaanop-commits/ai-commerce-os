from __future__ import annotations

import pytest

from app.services import listings as listing_service


def test_create_draft_requires_an_approved_primary_asset(db, make_organization, make_product, make_marketplace_connection):
    org = make_organization()
    product = make_product(org)
    connection = make_marketplace_connection(org)

    with pytest.raises(listing_service.NoApprovedPrimaryAssetError):
        listing_service.create_draft(db, org.id, product, connection)


def test_create_draft_succeeds_with_a_primary_asset(db, make_organization, make_product, make_primary_asset, make_marketplace_connection):
    org = make_organization()
    product = make_product(org, title="Wireless Mouse", price="19.99")
    make_primary_asset(product)
    connection = make_marketplace_connection(org)

    listing = listing_service.create_draft(db, org.id, product, connection)

    assert listing.status == "draft"
    assert listing.title == "Wireless Mouse"
    assert listing.listing_data["image_url"]


def test_create_draft_rejects_disconnected_connection(db, make_organization, make_product, make_primary_asset, make_marketplace_connection):
    org = make_organization()
    product = make_product(org)
    make_primary_asset(product)
    connection = make_marketplace_connection(org, status="disconnected")

    with pytest.raises(listing_service.ConnectionNotConnectedError):
        listing_service.create_draft(db, org.id, product, connection)


def _make_draft(db, make_organization, make_product, make_primary_asset, make_marketplace_connection, **product_kwargs):
    org = make_organization()
    product = make_product(org, **product_kwargs)
    make_primary_asset(product)
    connection = make_marketplace_connection(org)
    listing = listing_service.create_draft(db, org.id, product, connection)
    return org, product, connection, listing


def test_full_lifecycle_draft_to_active_to_ended(db, make_organization, make_product, make_primary_asset, make_marketplace_connection):
    org, product, connection, listing = _make_draft(db, make_organization, make_product, make_primary_asset, make_marketplace_connection)

    approved = listing_service.approve_listing(db, listing)
    assert approved.status == "approved"

    active = listing_service.publish_listing(db, listing)
    assert active.status == "active"
    assert active.external_listing_id is not None
    assert active.listing_data.get("marketplace_url")

    ended = listing_service.end_listing(db, listing)
    assert ended.status == "ended"


def test_publish_requires_approved_status(db, make_organization, make_product, make_primary_asset, make_marketplace_connection):
    org, product, connection, listing = _make_draft(db, make_organization, make_product, make_primary_asset, make_marketplace_connection)

    with pytest.raises(listing_service.InvalidListingTransitionError):
        listing_service.publish_listing(db, listing)


def test_publish_failure_transitions_to_error_and_is_retryable(db, make_organization, make_product, make_primary_asset, make_marketplace_connection):
    org, product, connection, listing = _make_draft(
        db, make_organization, make_product, make_primary_asset, make_marketplace_connection, title="__fail__ Widget"
    )
    listing_service.approve_listing(db, listing)

    from app.marketplaces.adapters.base import MarketplaceError

    with pytest.raises(MarketplaceError):
        listing_service.publish_listing(db, listing)

    assert listing.status == "error"
    assert listing.last_error == "marketplace_error"
    assert listing.external_listing_id is None

    # Fix the title (simulating a human editing it) and retry.
    listing.title = "Fixed Widget"
    db.commit()

    active = listing_service.retry_listing(db, listing)
    assert active.status == "active"
    assert active.external_listing_id is not None


def test_retry_requires_error_status(db, make_organization, make_product, make_primary_asset, make_marketplace_connection):
    org, product, connection, listing = _make_draft(db, make_organization, make_product, make_primary_asset, make_marketplace_connection)

    with pytest.raises(listing_service.InvalidListingTransitionError):
        listing_service.retry_listing(db, listing)


def test_end_requires_active_status(db, make_organization, make_product, make_primary_asset, make_marketplace_connection):
    org, product, connection, listing = _make_draft(db, make_organization, make_product, make_primary_asset, make_marketplace_connection)

    with pytest.raises(listing_service.InvalidListingTransitionError):
        listing_service.end_listing(db, listing)


def test_approve_requires_draft_status(db, make_organization, make_product, make_primary_asset, make_marketplace_connection):
    org, product, connection, listing = _make_draft(db, make_organization, make_product, make_primary_asset, make_marketplace_connection)
    listing_service.approve_listing(db, listing)

    with pytest.raises(listing_service.InvalidListingTransitionError):
        listing_service.approve_listing(db, listing)


def test_delete_draft_succeeds(db, make_organization, make_product, make_primary_asset, make_marketplace_connection):
    org, product, connection, listing = _make_draft(db, make_organization, make_product, make_primary_asset, make_marketplace_connection)
    listing_id = listing.id

    listing_service.delete_draft(db, listing)

    with pytest.raises(listing_service.ListingNotFoundError):
        listing_service.get_listing(db, org.id, product.id, listing_id)


def test_delete_non_draft_rejected(db, make_organization, make_product, make_primary_asset, make_marketplace_connection):
    org, product, connection, listing = _make_draft(db, make_organization, make_product, make_primary_asset, make_marketplace_connection)
    listing_service.approve_listing(db, listing)

    with pytest.raises(listing_service.InvalidListingTransitionError):
        listing_service.delete_draft(db, listing)


def test_get_listing_is_organization_scoped(db, make_organization, make_product, make_primary_asset, make_marketplace_connection):
    org_a, product_a, connection_a, listing_a = _make_draft(
        db, make_organization, make_product, make_primary_asset, make_marketplace_connection
    )
    org_b = make_organization()

    with pytest.raises(listing_service.ListingNotFoundError):
        listing_service.get_listing(db, org_b.id, product_a.id, listing_a.id)
