import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.schemas.users import UserCreate
from app.services.auth import verify_password
from app.services.users import DuplicateUsernameError, create_user, list_users, set_user_active


def test_create_user_hashes_password_and_defaults_active() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        user = create_user(
            database,
            UserCreate(username="newcashier", password="Str0ngPass!", full_name="New Cashier", role="cashier"),
        )
        assert user.is_active is True
        assert user.password_hash != "Str0ngPass!"
        assert verify_password("Str0ngPass!", user.password_hash)


def test_create_user_rejects_duplicate_username() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        create_user(
            database,
            UserCreate(username="dupe", password="Str0ngPass!", full_name="First", role="cashier"),
        )
        with pytest.raises(DuplicateUsernameError):
            create_user(
                database,
                UserCreate(username="dupe", password="Other12345", full_name="Second", role="manager"),
            )


def test_set_user_active_toggles_and_excludes_from_active_listing() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        user = create_user(
            database,
            UserCreate(username="tempuser", password="Str0ngPass!", full_name="Temp", role="accountant"),
        )
        set_user_active(database, user, False)
        active_users = list_users(database, active_only=True)
        assert user.username not in [u.username for u in active_users]

        all_users = list_users(database, active_only=False)
        assert user.username in [u.username for u in all_users]
