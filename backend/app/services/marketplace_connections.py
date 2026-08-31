from __future__ import annotations

import uuid

from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm import joinedload

from app.db.tenant import org_scoped
from app.models import Marketplace, MarketplaceConnection


class MarketplaceNotFoundError(Exception):
    pass


class MarketplaceConnectionNotFoundError(Exception):
    pass


def get_marketplace_by_key(db: DBSession, key: str) -> Marketplace:
    marketplace = db.query(Marketplace).filter(Marketplace.key == key).one_or_none()
    if marketplace is None:
        raise MarketplaceNotFoundError(key)
    return marketplace


def create_connection(
    db: DBSession,
    organization_id: uuid.UUID,
    *,
    marketplace_key: str,
    display_name: str | None = None,
) -> MarketplaceConnection:
    marketplace = get_marketplace_by_key(db, marketplace_key)

    connection = MarketplaceConnection(
        organization_id=organization_id,
        marketplace_id=marketplace.id,
        display_name=display_name,
        # No real credentials exist for any adapter implemented this phase --
        # explicitly NULL, never a placeholder value that could later be
        # mistaken for real ciphertext.
        credentials_ciphertext=None,
        status="connected",
    )
    db.add(connection)
    db.flush()
    connection.marketplace = marketplace
    return connection


def list_connections(db: DBSession, organization_id: uuid.UUID) -> list[MarketplaceConnection]:
    return (
        db.execute(
            org_scoped(MarketplaceConnection, organization_id)
            .options(joinedload(MarketplaceConnection.marketplace))
            .order_by(MarketplaceConnection.created_at.desc())
        )
        .scalars()
        .all()
    )


def get_connection(
    db: DBSession, organization_id: uuid.UUID, connection_id: uuid.UUID
) -> MarketplaceConnection:
    connection = (
        db.execute(
            org_scoped(MarketplaceConnection, organization_id)
            .options(joinedload(MarketplaceConnection.marketplace))
            .where(MarketplaceConnection.id == connection_id)
        )
        .scalars()
        .one_or_none()
    )
    if connection is None:
        raise MarketplaceConnectionNotFoundError(connection_id)
    return connection


def remove_connection(db: DBSession, connection: MarketplaceConnection) -> MarketplaceConnection:
    # Soft removal only -- listings.marketplace_connection_id cascades on a
    # real delete, which would silently destroy an org's listing history.
    # Disconnecting keeps the row (and every listing that references it)
    # intact; a disconnected connection just can't be used for new drafts
    # or publishes going forward.
    connection.status = "disconnected"
    db.flush()
    return connection
