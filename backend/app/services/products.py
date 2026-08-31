from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm import selectinload

from app.db.tenant import org_scoped
from app.models import Product

# API-facing field name -> ORM attribute name, for the few that differ
# ("metadata" is reserved on the declarative base, see app.models.product).
_UPDATE_FIELD_MAP = {"metadata": "metadata_"}
_UPDATABLE_FIELDS = {"sku", "title", "description", "status", "price", "currency", "metadata"}


class DuplicateSkuError(Exception):
    pass


class ProductNotFoundError(Exception):
    pass


def create_product(
    db: DBSession,
    organization_id: uuid.UUID,
    *,
    sku: str,
    title: str,
    description: str | None = None,
    price: Decimal | None = None,
    currency: str = "USD",
    metadata: dict | None = None,
) -> Product:
    product = Product(
        organization_id=organization_id,
        sku=sku.strip(),
        title=title.strip(),
        description=description,
        price=price,
        currency=currency.upper(),
        metadata_=metadata or {},
    )
    db.add(product)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateSkuError(sku) from exc
    return product


def get_product(db: DBSession, organization_id: uuid.UUID, product_id: uuid.UUID) -> Product:
    product = (
        db.execute(
            org_scoped(Product, organization_id)
            .options(selectinload(Product.assets))
            .where(Product.id == product_id, Product.deleted_at.is_(None))
        )
        .scalars()
        .one_or_none()
    )
    if product is None:
        raise ProductNotFoundError(product_id)
    return product


def list_products(db: DBSession, organization_id: uuid.UUID) -> list[Product]:
    return (
        db.execute(
            org_scoped(Product, organization_id)
            .options(selectinload(Product.assets))
            .where(Product.deleted_at.is_(None))
            .order_by(Product.created_at.desc())
        )
        .scalars()
        .all()
    )


def update_product(db: DBSession, product: Product, updates: dict) -> Product:
    for field, value in updates.items():
        if field not in _UPDATABLE_FIELDS:
            continue
        attr = _UPDATE_FIELD_MAP.get(field, field)
        if field == "sku" and isinstance(value, str):
            value = value.strip()
        if field == "currency" and isinstance(value, str):
            value = value.upper()
        setattr(product, attr, value)

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateSkuError(product.sku) from exc
    return product


def delete_product(db: DBSession, product: Product) -> None:
    product.deleted_at = datetime.now(timezone.utc)
    db.flush()
