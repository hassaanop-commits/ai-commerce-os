from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.models import Listing, MarketplaceConnection

ConnectionStatus = Literal["connected", "disconnected", "error", "expired"]
ListingStatus = Literal["draft", "approved", "publishing", "active", "error", "ended"]


class MarketplaceConnectionCreateRequest(BaseModel):
    marketplace_key: str = Field(min_length=1, max_length=30)
    display_name: str | None = Field(default=None, max_length=120)


class MarketplaceConnectionRead(BaseModel):
    id: uuid.UUID
    marketplace_key: str
    marketplace_name: str
    display_name: str | None
    status: ConnectionStatus
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_connection(cls, connection: "MarketplaceConnection") -> "MarketplaceConnectionRead":
        # Deliberately never touches credentials_ciphertext -- it has no
        # field on this model at all, so there's no path that could leak it.
        return cls(
            id=connection.id,
            marketplace_key=connection.marketplace.key,
            marketplace_name=connection.marketplace.name,
            display_name=connection.display_name,
            status=connection.status,
            created_at=connection.created_at,
        )


class ListingCreateRequest(BaseModel):
    marketplace_connection_id: uuid.UUID


class ListingRead(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    marketplace_connection_id: uuid.UUID
    marketplace_key: str
    title: str
    description: str | None
    price: Decimal | None
    currency: str
    status: ListingStatus
    external_listing_id: str | None
    marketplace_url: str | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_listing(cls, listing: "Listing") -> "ListingRead":
        return cls(
            id=listing.id,
            product_id=listing.product_id,
            marketplace_connection_id=listing.marketplace_connection_id,
            marketplace_key=listing.marketplace_connection.marketplace.key,
            title=listing.title,
            description=listing.description,
            price=listing.price,
            currency=listing.currency,
            status=listing.status,
            external_listing_id=listing.external_listing_id,
            marketplace_url=listing.listing_data.get("marketplace_url"),
            last_error=listing.last_error,
            created_at=listing.created_at,
            updated_at=listing.updated_at,
        )
