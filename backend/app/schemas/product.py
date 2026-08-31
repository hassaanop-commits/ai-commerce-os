from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.models import Product, ProductAsset

ProductStatus = Literal["draft", "active", "archived"]


class ProductCreateRequest(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    price: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    metadata: dict = Field(default_factory=dict)


class ProductUpdateRequest(BaseModel):
    sku: str | None = Field(default=None, min_length=1, max_length=100)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    status: ProductStatus | None = None
    price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    metadata: dict | None = None


class ProductAssetRead(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    source: str
    status: str
    approval_status: str
    url: str
    is_primary: bool
    position: int
    asset_type: str
    error_message: str | None
    ai_run_id: uuid.UUID | None
    derived_from_asset_id: uuid.UUID | None
    image_prompt: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_asset(cls, asset: "ProductAsset") -> "ProductAssetRead":
        # image_prompt isn't its own column -- it's read off the originating
        # AIRun's metadata (see app.ai.tools.product_images), so an upload
        # (no ai_run) always reads back None here rather than needing a
        # nullable duplicate column on product_assets.
        image_prompt = asset.ai_run.metadata_.get("image_prompt") if asset.ai_run is not None else None
        return cls(
            id=asset.id,
            product_id=asset.product_id,
            source=asset.source,
            status=asset.status,
            approval_status=asset.approval_status,
            url=asset.url,
            is_primary=asset.is_primary,
            position=asset.position,
            asset_type=asset.asset_type,
            error_message=asset.error_message,
            ai_run_id=asset.ai_run_id,
            derived_from_asset_id=asset.derived_from_asset_id,
            image_prompt=image_prompt,
            created_at=asset.created_at,
        )


class ProductRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    sku: str
    title: str
    description: str | None
    status: str
    price: Decimal | None
    currency: str
    metadata: dict
    primary_asset: ProductAssetRead | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_product(cls, product: "Product") -> "ProductRead":
        primary = next((asset for asset in product.assets if asset.is_primary), None)
        return cls(
            id=product.id,
            organization_id=product.organization_id,
            sku=product.sku,
            title=product.title,
            description=product.description,
            status=product.status,
            price=product.price,
            currency=product.currency,
            metadata=product.metadata_,
            primary_asset=ProductAssetRead.from_asset(primary) if primary else None,
            created_at=product.created_at,
            updated_at=product.updated_at,
        )


class ProductAssetUpdateRequest(BaseModel):
    is_primary: bool | None = None
    position: int | None = Field(default=None, ge=0)
