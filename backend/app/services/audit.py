from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session as DBSession

from app.models import AuditLog

logger = logging.getLogger(__name__)


def record_event(
    db: DBSession,
    event_type: str,
    *,
    actor_user_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    ip_address: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Best-effort audit write.

    Callers invoke this only after the operation it records has already
    committed (or, for pure read-only failures like a bad login, is otherwise
    complete) -- never as a mid-transaction step -- so this function's own
    commit can't interact with in-flight changes belonging to something else.
    It never raises: a broken audit sink must not be able to take down
    authentication or organization management. `metadata` must never contain
    passwords, hashes, or raw tokens -- callers are responsible for that; this
    function only ever stores what it's given.
    """
    entry = AuditLog(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        target_type=target_type,
        target_id=target_id,
        ip_address=ip_address,
        metadata_=metadata or {},
    )
    try:
        db.add(entry)
        db.commit()
    except Exception as exc:  # noqa: BLE001 -- must never propagate to the caller
        db.rollback()
        logger.warning("audit log write failed for event_type=%s (%s)", event_type, type(exc).__name__)
