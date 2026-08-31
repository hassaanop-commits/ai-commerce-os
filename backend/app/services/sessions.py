from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session as DBSession

from app.core.config import settings
from app.models import Session as SessionModel
from app.models import User

# Throttles how often a valid request extends the session, so sliding expiration
# doesn't turn into a DB write on every single authenticated request.
_TOUCH_THROTTLE = timedelta(minutes=5)


def session_cookie_max_age_seconds() -> int:
    return settings.session_idle_ttl_days * 24 * 60 * 60


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_session(
    db: DBSession,
    user: User,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[SessionModel, str]:
    raw_token = generate_session_token()
    now = datetime.now(timezone.utc)
    session = SessionModel(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        expires_at=now + timedelta(days=settings.session_idle_ttl_days),
        last_seen_at=now,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session, raw_token


def get_valid_session(db: DBSession, raw_token: str) -> SessionModel | None:
    token_hash = hash_token(raw_token)
    session = db.query(SessionModel).filter(SessionModel.token_hash == token_hash).one_or_none()
    if session is None:
        return None
    now = datetime.now(timezone.utc)
    if session.revoked_at is not None or session.expires_at <= now:
        return None
    return session


def touch_session(db: DBSession, session: SessionModel) -> None:
    now = datetime.now(timezone.utc)
    if now - session.last_seen_at < _TOUCH_THROTTLE:
        return
    absolute_cap = session.created_at + timedelta(days=settings.session_absolute_ttl_days)
    session.last_seen_at = now
    session.expires_at = min(now + timedelta(days=settings.session_idle_ttl_days), absolute_cap)
    db.commit()


def revoke_session(db: DBSession, session: SessionModel) -> None:
    session.revoked_at = datetime.now(timezone.utc)
    db.commit()


def revoke_all_sessions_for_user(db: DBSession, user: User) -> None:
    now = datetime.now(timezone.utc)
    db.query(SessionModel).filter(
        SessionModel.user_id == user.id, SessionModel.revoked_at.is_(None)
    ).update({"revoked_at": now})
    db.commit()
