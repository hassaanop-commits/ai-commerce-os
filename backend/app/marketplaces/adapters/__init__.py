from __future__ import annotations

from app.marketplaces.adapters.base import ListingPayload, MarketplaceAdapter, MarketplaceError, PublishResult
from app.marketplaces.adapters.manual_adapter import ManualMarketplaceAdapter

_ADAPTERS: dict[str, MarketplaceAdapter] = {}


def _build_adapter(key: str) -> MarketplaceAdapter:
    if key == "manual":
        return ManualMarketplaceAdapter()
    # Real adapters (Shopify, Amazon, eBay, Etsy, WooCommerce, ...) are not
    # implemented yet -- resolving one raises the same sanitized category a
    # real adapter would raise for an unconfigured connection.
    raise MarketplaceError("connection_not_configured", f"No adapter is available for marketplace '{key}'.")


def get_marketplace_adapter(key: str) -> MarketplaceAdapter:
    # Adapters are cheap, stateless clients -- cached per marketplace key
    # exactly like app.ai.providers.get_provider().
    if key not in _ADAPTERS:
        _ADAPTERS[key] = _build_adapter(key)
    return _ADAPTERS[key]


__all__ = [
    "ListingPayload",
    "MarketplaceAdapter",
    "MarketplaceError",
    "PublishResult",
    "get_marketplace_adapter",
]
