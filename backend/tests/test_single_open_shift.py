"""Only one till session may be open, enforced by the database itself.

services/shifts.py::open_shift() has always checked this in Python, but
check-then-insert is not atomic — two requests can both see no open shift
and both insert. These tests go around the service entirely and write the
rows directly, which is the only way to show the constraint is real rather
than a Python convention.

Why it is worth a database constraint: close_shift() gives its cash-out
queries no upper time bound, on the stated grounds that only one shift is
ever open. Those queries match on a timestamp and nothing else, so two
overlapping open shifts would subtract the same cash expense from both
reconciliations, and each till would report a shortage for money that left
the drawer once.
"""

from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import CashierShift, ShiftStatus, User
from app.services.shifts import ShiftError, close_shift, open_shift


def _cashier(database: Session, username: str) -> User:
    user = User(
        username=username,
        password_hash="x",
        full_name=username.title(),
        role="cashier",
        is_active=True,
    )
    database.add(user)
    database.commit()
    database.refresh(user)
    return user


def _raw_open_shift(database: Session, cashier: User) -> CashierShift:
    """Insert an OPEN shift directly, bypassing open_shift()'s guard."""
    shift = CashierShift(
        cashier_id=cashier.id, opening_cash=Decimal("0"), status=ShiftStatus.OPEN
    )
    database.add(shift)
    database.commit()
    return shift


def test_database_rejects_a_second_open_shift_even_bypassing_the_service(
    db_session: Session,
) -> None:
    first = _cashier(db_session, "cashier_one")
    second = _cashier(db_session, "cashier_two")

    _raw_open_shift(db_session, first)

    # No call to open_shift(): this is what a race, a stray script or a
    # direct SQL insert would do, and the database has to be the thing
    # that says no.
    with pytest.raises(IntegrityError):
        _raw_open_shift(db_session, second)

    db_session.rollback()
    assert (
        db_session.query(CashierShift).filter_by(status=ShiftStatus.OPEN).count() == 1
    )


def test_service_still_reports_a_clean_error_rather_than_an_integrityerror(
    db_session: Session,
) -> None:
    """The Python guard stays: a cashier should see the sentence, not a
    database exception leaking through the API."""
    first = _cashier(db_session, "cashier_one")
    second = _cashier(db_session, "cashier_two")

    open_shift(db_session, cashier_id=first.id, opening_cash=Decimal("100"))

    with pytest.raises(ShiftError, match="already open"):
        open_shift(db_session, cashier_id=second.id, opening_cash=Decimal("50"))


def test_any_number_of_closed_shifts_coexist(db_session: Session) -> None:
    """The constraint is partial — it must not turn into "one shift ever"."""
    cashier = _cashier(db_session, "cashier_one")

    for _ in range(3):
        shift = open_shift(db_session, cashier_id=cashier.id, opening_cash=Decimal("10"))
        close_shift(db_session, shift, closing_cash=Decimal("10"))

    assert db_session.query(CashierShift).count() == 3
    assert (
        db_session.query(CashierShift).filter_by(status=ShiftStatus.CLOSED).count() == 3
    )

    # And a fresh one may still be opened afterwards.
    open_shift(db_session, cashier_id=cashier.id, opening_cash=Decimal("10"))
    assert (
        db_session.query(CashierShift).filter_by(status=ShiftStatus.OPEN).count() == 1
    )
