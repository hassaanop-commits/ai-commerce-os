from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DBSession

from app.api.deps import require_admin, require_member
from app.api.http_utils import client_ip
from app.db.session import get_db
from app.models import OrganizationMember
from app.schemas.marketplace import MarketplaceConnectionCreateRequest, MarketplaceConnectionRead
from app.services import marketplace_connections as connection_service
from app.services.audit import record_event

router = APIRouter(prefix="/organizations/{org_id}/marketplace-connections", tags=["marketplace-connections"])


@router.get("", response_model=list[MarketplaceConnectionRead])
def list_marketplace_connections(
    membership: Annotated[OrganizationMember, Depends(require_member)],
    db: Annotated[DBSession, Depends(get_db)],
) -> list[MarketplaceConnectionRead]:
    connections = connection_service.list_connections(db, membership.organization_id)
    return [MarketplaceConnectionRead.from_connection(c) for c in connections]


@router.post("", response_model=MarketplaceConnectionRead, status_code=status.HTTP_201_CREATED)
def create_marketplace_connection(
    payload: MarketplaceConnectionCreateRequest,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_admin)],
    db: Annotated[DBSession, Depends(get_db)],
) -> MarketplaceConnectionRead:
    try:
        connection = connection_service.create_connection(
            db,
            membership.organization_id,
            marketplace_key=payload.marketplace_key,
            display_name=payload.display_name,
        )
    except connection_service.MarketplaceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown marketplace.") from exc

    db.commit()
    db.refresh(connection)

    record_event(
        db,
        "marketplace_connection_created",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="marketplace_connection",
        target_id=connection.id,
        metadata={"marketplace_key": payload.marketplace_key},
        ip_address=client_ip(request),
    )

    return MarketplaceConnectionRead.from_connection(connection)


@router.delete("/{connection_id}", response_model=MarketplaceConnectionRead)
def remove_marketplace_connection(
    connection_id: uuid.UUID,
    request: Request,
    membership: Annotated[OrganizationMember, Depends(require_admin)],
    db: Annotated[DBSession, Depends(get_db)],
) -> MarketplaceConnectionRead:
    try:
        connection = connection_service.get_connection(db, membership.organization_id, connection_id)
    except connection_service.MarketplaceConnectionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found.") from exc

    updated = connection_service.remove_connection(db, connection)
    db.commit()
    db.refresh(updated)

    record_event(
        db,
        "marketplace_connection_removed",
        actor_user_id=membership.user_id,
        organization_id=membership.organization_id,
        target_type="marketplace_connection",
        target_id=updated.id,
        ip_address=client_ip(request),
    )

    return MarketplaceConnectionRead.from_connection(updated)
