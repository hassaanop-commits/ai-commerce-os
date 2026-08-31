from datetime import datetime, timedelta, timezone

from app.models import Session as SessionModel
from app.services.sessions import (
    create_session,
    get_valid_session,
    hash_token,
    revoke_all_sessions_for_user,
    revoke_session,
)


def test_session_creation_stores_only_the_hash(db, make_user):
    user = make_user()
    session, raw_token = create_session(db, user)

    assert session.token_hash == hash_token(raw_token)
    assert session.token_hash != raw_token

    stored = db.query(SessionModel).filter(SessionModel.id == session.id).one()
    assert stored.token_hash == hash_token(raw_token)
    assert raw_token not in (stored.token_hash or "")


def test_valid_session_authentication(db, make_user):
    user = make_user()
    session, raw_token = create_session(db, user)

    found = get_valid_session(db, raw_token)

    assert found is not None
    assert found.id == session.id


def test_expired_session_rejected(db, make_user):
    user = make_user()
    session, raw_token = create_session(db, user)
    session.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()

    assert get_valid_session(db, raw_token) is None


def test_revoked_session_rejected(db, make_user):
    user = make_user()
    session, raw_token = create_session(db, user)
    revoke_session(db, session)

    assert session.revoked_at is not None
    assert get_valid_session(db, raw_token) is None


def test_missing_session_rejected(db):
    assert get_valid_session(db, "this-token-does-not-exist") is None


def test_revoke_all_sessions_for_user(db, make_user):
    user = make_user()
    _, token_a = create_session(db, user)
    _, token_b = create_session(db, user)

    revoke_all_sessions_for_user(db, user)

    assert get_valid_session(db, token_a) is None
    assert get_valid_session(db, token_b) is None


def test_revoke_all_sessions_does_not_affect_other_users(db, make_user):
    user_a = make_user()
    user_b = make_user()
    _, token_a = create_session(db, user_a)
    _, token_b = create_session(db, user_b)

    revoke_all_sessions_for_user(db, user_a)

    assert get_valid_session(db, token_a) is None
    assert get_valid_session(db, token_b) is not None
