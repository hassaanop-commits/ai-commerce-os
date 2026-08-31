from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.core.security import hash_password, verify_password
from app.models import User
from app.services.audit import record_event
from app.services.auth_tokens import (
    EMAIL_VERIFICATION_TTL,
    PASSWORD_RESET_TTL,
    consume_auth_token,
    create_auth_token,
)
from app.services.email import EmailService
from app.services.organizations import add_member, create_organization
from app.services.sessions import revoke_all_sessions_for_user

# Hashed once at import time so a login against an unknown email still pays the
# cost of an Argon2 verify — keeping response timing close to the wrong-password case.
_DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


class EmailAlreadyRegisteredError(Exception):
    pass


def signup(
    db: DBSession,
    email_service: EmailService,
    email: str,
    password: str,
    full_name: str,
    ip_address: str | None = None,
) -> User:
    email = email.strip().lower()
    full_name = full_name.strip()

    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        status="active",
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise EmailAlreadyRegisteredError from exc

    org_name = f"{full_name}'s Workspace" if full_name else "My Workspace"
    organization = create_organization(db, org_name, created_by=user)
    add_member(db, organization, user, role_key="owner", status="active")

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise EmailAlreadyRegisteredError from exc

    db.refresh(user)

    # A separate, smaller transaction: account creation succeeding is the part
    # that must be atomic (and already committed above). If token creation or
    # sending the email fails, the account still exists and remains usable --
    # not something that should roll back a successful signup.
    _, raw_token = create_auth_token(db, user, purpose="email_verification", ttl=EMAIL_VERIFICATION_TTL)
    db.commit()
    email_service.send_verification_email(user.email, raw_token)

    record_event(
        db, "signup", actor_user_id=user.id, organization_id=organization.id, ip_address=ip_address
    )

    return user


def verify_email(db: DBSession, raw_token: str, ip_address: str | None = None) -> User | None:
    token = consume_auth_token(db, raw_token, purpose="email_verification")
    if token is None:
        return None
    user = token.user
    user.email_verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    record_event(db, "email_verified", actor_user_id=user.id, ip_address=ip_address)

    return user


def request_password_reset(
    db: DBSession, email_service: EmailService, email: str, ip_address: str | None = None
) -> None:
    email = email.strip().lower()
    user = db.query(User).filter(User.email == email).one_or_none()
    # Always a no-op from the caller's point of view whether or not the
    # account exists -- the route returns the exact same response either way.
    # The audit trail is internal-only, so both branches are still recorded
    # (a burst of requests for unknown emails is itself a signal worth having).
    if user is None or user.hashed_password is None:
        record_event(
            db, "password_reset_requested", actor_user_id=None, ip_address=ip_address, metadata={"email": email}
        )
        return
    _, raw_token = create_auth_token(db, user, purpose="password_reset", ttl=PASSWORD_RESET_TTL)
    db.commit()
    email_service.send_password_reset_email(user.email, raw_token)

    record_event(db, "password_reset_requested", actor_user_id=user.id, ip_address=ip_address)


def reset_password(db: DBSession, raw_token: str, new_password: str, ip_address: str | None = None) -> User | None:
    token = consume_auth_token(db, raw_token, purpose="password_reset")
    if token is None:
        return None
    user = token.user
    user.hashed_password = hash_password(new_password)
    db.commit()
    revoke_all_sessions_for_user(db, user)
    db.refresh(user)

    record_event(db, "password_reset_completed", actor_user_id=user.id, ip_address=ip_address)

    return user


def authenticate(db: DBSession, email: str, password: str) -> User | None:
    email = email.strip().lower()
    user = db.query(User).filter(User.email == email).one_or_none()

    if user is None or user.hashed_password is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        return None

    if not verify_password(password, user.hashed_password):
        return None

    if user.status != "active":
        return None

    return user
