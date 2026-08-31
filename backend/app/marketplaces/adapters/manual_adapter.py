from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.marketplaces.adapters.base import ListingPayload, MarketplaceError, PublishResult

if TYPE_CHECKING:
    from app.models import MarketplaceConnection


class ManualMarketplaceAdapter:
    """Deterministic, network-free adapter used by tests and as the only
    real marketplace wired up in this phase -- proves the entire connect ->
    draft -> approve -> publish -> end pipeline without any real
    marketplace account, exactly like MockProvider does for AI generation.

    A title or description containing the literal string "__fail__"
    triggers a MarketplaceError, for exercising the failure path without a
    real outage.
    """

    name = "manual"

    def create_listing(self, *, connection: "MarketplaceConnection", payload: ListingPayload) -> PublishResult:
        if "__fail__" in payload.title or "__fail__" in payload.description:
            raise MarketplaceError("marketplace_error", "Manual adapter was asked to fail.")

        external_id = f"manual-{uuid.uuid4().hex[:12]}"
        return PublishResult(
            external_listing_id=external_id, marketplace_url=f"https://manual.test/listings/{external_id}"
        )

    def end_listing(self, *, connection: "MarketplaceConnection", external_listing_id: str) -> None:
        if "__fail__" in external_listing_id:
            raise MarketplaceError("marketplace_error", "Manual adapter was asked to fail.")
        # No-op -- there's no real external system to notify.
        return None
