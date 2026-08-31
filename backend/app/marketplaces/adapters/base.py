from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.models import MarketplaceConnection


@dataclass(frozen=True)
class ListingPayload:
    title: str
    description: str
    price: Decimal | None
    currency: str
    image_url: str | None


@dataclass(frozen=True)
class PublishResult:
    external_listing_id: str
    marketplace_url: str | None = None


class MarketplaceError(Exception):
    """Raised for any adapter failure, carrying only a sanitized category.

    `category` is one of a small closed set (see app.services.listings) that
    is safe to persist on a Listing row and show to a user -- mirrors
    app.ai.providers.base.ProviderError. The original exception, if any, is
    available on `__cause__` for server-side logging only.
    """

    def __init__(self, category: str, message: str | None = None) -> None:
        super().__init__(message or category)
        self.category = category


class MarketplaceAdapter(Protocol):
    name: str

    def create_listing(self, *, connection: "MarketplaceConnection", payload: ListingPayload) -> PublishResult:
        """Publish a listing. Raises MarketplaceError on failure."""
        ...

    def end_listing(self, *, connection: "MarketplaceConnection", external_listing_id: str) -> None:
        """Delist/end a previously published listing. Raises MarketplaceError on failure."""
        ...
