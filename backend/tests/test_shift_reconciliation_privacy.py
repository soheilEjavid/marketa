"""The verdict on a cash count is not for the person who counted.

A shortage or an overage is a question about the cashier, so they should
not read it off their own screen. Hiding it in the interface would be
theatre — the number would still be one developer-tools panel away — so it
is withheld from the payload itself, on the server, like every other role
rule here.

What a cashier keeps: opening the shift, entering the counted cash, and
closing it. What they lose: `expected_cash` and `difference`.
"""

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes import shifts as shift_routes
from app.models.base import Base
from app.models.entities import Product, User
from app.schemas.shifts import ShiftCloseRequest, ShiftOpenRequest
from app.schemas.sale import SaleCreate, SaleItemCreate, SalePaymentLineInput
from app.services.sales import process_sale
from app.services.shifts import open_shift


ROLES_THAT_MAY_SEE = ["admin", "manager", "accountant"]
ROLES_THAT_MAY_NOT = ["cashier", "inventory_manager"]


def _setup() -> tuple[sessionmaker, dict[str, int], int]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with Sessions() as database:
        product = Product(name="کالا", purchase_price=Decimal("1000"), sale_price=Decimal("2000"),
                          stock_quantity=Decimal("100"), low_stock_threshold=Decimal("0"), is_active=True)
        database.add(product)
        users = {}
        for role in ROLES_THAT_MAY_SEE + ROLES_THAT_MAY_NOT:
            user = User(username=role, password_hash="x", full_name=role, role=role)
            database.add(user)
            database.flush()
            users[role] = user.id
        database.commit()

        shift = open_shift(database, cashier_id=users["cashier"], opening_cash=Decimal("100000"))
        process_sale(database, SaleCreate(
            invoice_number="S-1",
            items=[SaleItemCreate(product_id=product.id, quantity=Decimal("10"))],
            payment_lines=[SalePaymentLineInput(method="cash", amount=Decimal("20000"))]))
        return Sessions, users, shift.id


def _as(database, users, role):
    return database.get(User, users[role])


@pytest.mark.parametrize("role", ROLES_THAT_MAY_SEE)
def test_a_manager_closing_a_shift_sees_the_reconciliation(role) -> None:
    Sessions, users, shift_id = _setup()
    with Sessions() as database:
        closed = asyncio.run(shift_routes.close_shift(
            shift_id, ShiftCloseRequest(closing_cash=Decimal("115000")),
            database, _as(database, users, role)))
        assert closed["expected_cash"] == Decimal("120000.00")
        assert closed["difference"] == Decimal("-5000.00"), "5,000 short, and they are told"


@pytest.mark.parametrize("role", ROLES_THAT_MAY_NOT)
def test_a_cashier_closes_the_shift_but_is_not_told_how_it_came_out(role) -> None:
    Sessions, users, shift_id = _setup()
    with Sessions() as database:
        closed = asyncio.run(shift_routes.close_shift(
            shift_id, ShiftCloseRequest(closing_cash=Decimal("115000")),
            database, _as(database, users, role)))
        # The count itself still lands — closing is their job.
        assert closed["status"] == "closed"
        assert closed["closing_cash"] == Decimal("115000.00")
        assert closed["expected_cash"] is None, "withheld from the payload, not just the screen"
        assert closed["difference"] is None


def test_the_figures_are_still_recorded_for_whoever_may_read_them() -> None:
    """Withholding is a display decision — the shift row keeps the truth,
    or the manager would have nothing to review."""
    from app.models.entities import CashierShift

    Sessions, users, shift_id = _setup()
    with Sessions() as database:
        asyncio.run(shift_routes.close_shift(
            shift_id, ShiftCloseRequest(closing_cash=Decimal("115000")),
            database, _as(database, users, "cashier")))
    with Sessions() as database:
        stored = database.get(CashierShift, shift_id)
        assert stored.expected_cash == Decimal("120000.00")
        assert stored.difference == Decimal("-5000.00")

        # And a manager reading the same shift back gets them.
        seen = asyncio.run(shift_routes.get_shift(
            shift_id, database, _as(database, users, "manager")))
        assert seen["difference"] == Decimal("-5000.00")


def test_every_shift_route_honours_the_rule() -> None:
    """A single unguarded route would hand the number back anyway."""
    Sessions, users, shift_id = _setup()
    with Sessions() as database:
        cashier = _as(database, users, "cashier")
        asyncio.run(shift_routes.close_shift(
            shift_id, ShiftCloseRequest(closing_cash=Decimal("115000")), database, cashier))

        listed = asyncio.run(shift_routes.list_shifts(database, 200, cashier))
        assert all(row["difference"] is None for row in listed)

        one = asyncio.run(shift_routes.get_shift(shift_id, database, cashier))
        assert one["difference"] is None

        current = asyncio.run(shift_routes.get_current_shift(database, cashier))
        assert current is None, "the shift was just closed"

        reopened = asyncio.run(shift_routes.open_shift(
            ShiftOpenRequest(cashier_id=users["cashier"], opening_cash=Decimal("50000")),
            database, cashier))
        assert reopened["difference"] is None
        live = asyncio.run(shift_routes.get_current_shift(database, cashier))
        assert live["difference"] is None
