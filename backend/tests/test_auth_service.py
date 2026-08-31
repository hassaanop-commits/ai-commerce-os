from __future__ import annotations

import pytest
from sqlalchemy.exc import NoResultFound

from app.models import Role, User
from app.services import auth as auth_service
from app.services.email import ConsoleEmailService


def test_signup_rolls_back_fully_if_membership_step_fails(db):
    owner_role = db.query(Role).filter(Role.key == "owner").one()
    db.delete(owner_role)
    db.commit()

    with pytest.raises(NoResultFound):
        auth_service.signup(
            db,
            ConsoleEmailService(),
            email="rollback.test@example.com",
            password="a-very-strong-password-123",
            full_name="Rollback Test",
        )

    db.rollback()

    assert db.query(User).filter(User.email == "rollback.test@example.com").one_or_none() is None
