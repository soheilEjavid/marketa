"""First-admin creation on a fresh install.

The installed product ships an empty database and has no auth bypass, so
this one account is the only way into a new shop — and it must be created
exactly once, no matter how many times the installer or a retry runs it.
"""

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.bootstrap import _decode_password, create_first_admin
from app.models.entities import User
from app.services.auth import verify_password


def _user_count(db_session) -> int:
    return db_session.scalar(select(func.count()).select_from(User))


def test_creates_an_active_admin_on_an_empty_database(db_session):
    created = create_first_admin(
        db_session,
        username="owner",
        password="Owner@12345",
        full_name="مالک فروشگاه",
    )

    assert created is True
    user = db_session.scalars(select(User)).one()
    assert user.username == "owner"
    assert user.full_name == "مالک فروشگاه"
    assert user.role == "admin"
    assert user.is_active is True
    # Stored as a bcrypt hash, verifiable by the same function login uses.
    assert user.password_hash != "Owner@12345"
    assert verify_password("Owner@12345", user.password_hash)


def test_second_run_creates_nothing_and_reports_it(db_session):
    assert create_first_admin(
        db_session, username="owner", password="Owner@12345", full_name="مالک"
    )

    created = create_first_admin(
        db_session, username="intruder", password="Intruder@123", full_name="X"
    )

    assert created is False
    assert _user_count(db_session) == 1
    assert db_session.scalars(select(User)).one().username == "owner"


def test_any_existing_user_blocks_bootstrap_not_just_an_admin(db_session):
    # A shop that has already been set up may well have had its owner
    # account renamed or deactivated; the presence of *any* user means the
    # install is not fresh and must not gain a new admin with a password
    # whoever ran the installer chose.
    db_session.add(
        User(
            username="cashier",
            password_hash="irrelevant",
            full_name="صندوق‌دار",
            role="cashier",
        )
    )
    db_session.commit()

    created = create_first_admin(
        db_session, username="owner", password="Owner@12345", full_name="مالک"
    )

    assert created is False
    assert _user_count(db_session) == 1


def test_password_rules_match_the_api_and_nothing_is_written(db_session):
    with pytest.raises(ValidationError):
        create_first_admin(
            db_session, username="owner", password="short", full_name="مالک"
        )

    assert _user_count(db_session) == 0


def test_username_rules_match_the_api(db_session):
    with pytest.raises(ValidationError):
        create_first_admin(
            db_session, username="ab", password="Owner@12345", full_name="مالک"
        )

    assert _user_count(db_session) == 0


@pytest.mark.parametrize(
    "encoding",
    [
        "utf-8",
        # What a Unicode NSIS installer's FileWrite actually produces —
        # decoding it as UTF-8 yields a password nobody can type again.
        "utf-16",
        "utf-16-le",
        "utf-8-sig",
    ],
)
def test_password_file_survives_every_encoding_the_wizard_might_write(encoding):
    password = "رمزOwner@123"
    assert _decode_password(password.encode(encoding)) == password
