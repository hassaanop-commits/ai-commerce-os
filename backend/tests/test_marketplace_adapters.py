from __future__ import annotations

import pytest

from app.marketplaces.adapters.base import ListingPayload, MarketplaceError
from app.marketplaces.adapters.manual_adapter import ManualMarketplaceAdapter


def _payload(title: str = "Widget", description: str = "A fine widget.") -> ListingPayload:
    return ListingPayload(title=title, description=description, price=None, currency="USD", image_url="/file")


def test_manual_adapter_creates_a_deterministic_listing():
    adapter = ManualMarketplaceAdapter()

    result = adapter.create_listing(connection=None, payload=_payload())

    assert result.external_listing_id.startswith("manual-")
    assert result.marketplace_url is not None
    assert result.external_listing_id in result.marketplace_url


def test_manual_adapter_create_listing_raises_on_fail_sentinel():
    adapter = ManualMarketplaceAdapter()

    with pytest.raises(MarketplaceError) as exc_info:
        adapter.create_listing(connection=None, payload=_payload(title="__fail__ Widget"))

    assert exc_info.value.category == "marketplace_error"


def test_manual_adapter_end_listing_succeeds():
    adapter = ManualMarketplaceAdapter()

    # No exception, no return value -- just must not raise.
    assert adapter.end_listing(connection=None, external_listing_id="manual-abc123") is None


def test_manual_adapter_end_listing_raises_on_fail_sentinel():
    adapter = ManualMarketplaceAdapter()

    with pytest.raises(MarketplaceError) as exc_info:
        adapter.end_listing(connection=None, external_listing_id="manual-__fail__")

    assert exc_info.value.category == "marketplace_error"


def test_unknown_marketplace_key_raises_connection_not_configured():
    from app.marketplaces.adapters import get_marketplace_adapter

    with pytest.raises(MarketplaceError) as exc_info:
        get_marketplace_adapter("shopify")

    assert exc_info.value.category == "connection_not_configured"
