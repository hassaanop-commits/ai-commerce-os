from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session as DBSession

from app.models import AuthToken, User

EMAIL_VERIFICATION_TTL = timedelta(hours=24)
PASSWORD_RESET_TTL = timedelta(hours=1)
INVITE_ACCEPT_TTL = timedelta(days=7)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_auth_token(db: DBSession, user: User, purpose: str, ttl: timedelta) -> tuple[AuthToken, str]:
    raw_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    token = AuthToken(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        purpose=purpose,
        expires_at=now + ttl,
    )
    db.add(token)
    db.flush()
    return token, raw_token


def consume_auth_token(db: DBSession, raw_token: str, purpose: str) -> AuthToken | None:
    token = db.query(AuthToken).filter(AuthToken.token_hash == hash_token(raw_token)).one_or_none()
    if token is None:
        return None
    now = datetime.now(timezone.utc)
    # Wrong purpose, already used, or expired are all treated identically by the
    # caller (a generic "invalid or expired" response) -- this function just
    # decides validity, single-use, and replay-safety in one place.
    if token.purpose != purpose or token.used_at is not None or token.expires_at <= now:
        return None
    token.used_at = now
    db.flush()
    return token
