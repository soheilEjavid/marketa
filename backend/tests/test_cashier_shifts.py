from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.entities import Customer, DocumentStatus, Product, User
from app.schemas.financial import PaymentCreate
from app.schemas.sale import SaleCreate, SaleItemCreate, SalePaymentLineInput
from app.services.financials import record_customer_payment
from app.services.sales import (
    SaleError,
    cancel_held_sale,
    hold_sale,
    list_held_sales,
    list_sales,
    process_sale,
)
from app.services.shifts import ShiftError, close_shift, get_open_shift, get_shift, open_shift


def _make_product(database: Session, stock: str = "100") -> Product:
    product = Product(
        name="Tea",
        purchase_price=Decimal("5"),
        sale_price=Decimal("10"),
        stock_quantity=Decimal(stock),
        low_stock_threshold=Decimal("2"),
        is_active=True,
    )
    database.add(product)
    database.commit()
    database.refresh(product)
    return product


def _make_cashier(database: Session, username: str = "cashier1") -> User:
    user = User(
        username=username,
        password_hash="x",
        full_name="Test Cashier",
        role="cashier",
        is_active=True,
    )
    database.add(user)
    database.commit()
    database.refresh(user)
    return user


def test_hold_sale_does_not_touch_stock_or_balance() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        product = _make_product(database)

        held = hold_sale(
            database,
            SaleCreate(items=[SaleItemCreate(product_id=product.id, quantity=Decimal("3"))]),
        )

        assert held.status == DocumentStatus.DRAFT
        assert held.total == Decimal("30.00")
        database.refresh(product)
        assert product.stock_quantity == Decimal("100")  # unchanged
        assert list_sales(database) == []  # drafts excluded from history


def test_resume_then_complete_decrements_stock_exactly_once() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        product = _make_product(database)

        held = hold_sale(
            database,
            SaleCreate(items=[SaleItemCreate(product_id=product.id, quantity=Decimal("3"))]),
        )
        assert len(list_held_sales(database)) == 1

        # Resume: mark the draft cancelled, then complete a fresh sale for
        # the same cart contents — mirrors the frontend's rehydrate flow.
        cancel_held_sale(database, held)
        assert held.status == DocumentStatus.CANCELLED
        assert list_held_sales(database) == []

        completed = process_sale(
            database,
            SaleCreate(items=[SaleItemCreate(product_id=product.id, quantity=Decimal("3"))]),
        )
        assert completed.status == DocumentStatus.COMPLETED

        database.refresh(product)
        assert product.stock_quantity == Decimal("97")  # decremented exactly once
        assert len(list_sales(database)) == 1  # only the completed sale is visible


def test_discard_held_sale_never_touched_stock() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        product = _make_product(database)
        held = hold_sale(
            database,
            SaleCreate(items=[SaleItemCreate(product_id=product.id, quantity=Decimal("5"))]),
        )
        cancel_held_sale(database, held)

        database.refresh(product)
        assert product.stock_quantity == Decimal("100")
        assert list_sales(database) == []

        with pytest.raises(SaleError):
            cancel_held_sale(database, held)  # already cancelled — can't discard/resume twice


def test_single_open_shift_enforced() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        cashier = _make_cashier(database)
        open_shift(database, cashier_id=cashier.id, opening_cash=Decimal("500000"))
        with pytest.raises(ShiftError):
            open_shift(database, cashier_id=cashier.id, opening_cash=Decimal("0"))


def test_shift_reconciliation_matches_cash_sales() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        product = _make_product(database)
        cashier = _make_cashier(database)

        shift = open_shift(database, cashier_id=cashier.id, opening_cash=Decimal("100000"))
        assert get_open_shift(database).id == shift.id

        cash_sale = process_sale(
            database,
            SaleCreate(payment_method="cash", items=[SaleItemCreate(product_id=product.id, quantity=Decimal("2"))]),
        )
        assert cash_sale.shift_id == shift.id
        assert cash_sale.paid_amount == Decimal("20.00")

        # A card sale shouldn't count toward expected cash.
        process_sale(
            database,
            SaleCreate(payment_method="card", items=[SaleItemCreate(product_id=product.id, quantity=Decimal("1"))]),
        )

        closed = close_shift(database, get_shift(database, shift.id), closing_cash=Decimal("100020"))
        assert closed.expected_cash == Decimal("100020.00")  # 100000 + 20 cash sale, card excluded
        assert closed.difference == Decimal("0.00")
        assert get_open_shift(database) is None

        with pytest.raises(ShiftError):
            close_shift(database, closed, closing_cash=Decimal("0"))


def test_shift_reconciliation_counts_only_cash_portion_of_split_payment_sale() -> None:
    """A single sale split cash+card must only contribute its cash line to
    expected_cash, not its full total (the whole point of this task)."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        product = _make_product(database)
        cashier = _make_cashier(database)

        shift = open_shift(database, cashier_id=cashier.id, opening_cash=Decimal("100000"))

        # total = 10 * 10 = 100, split 60 cash / 40 card.
        sale = process_sale(
            database,
            SaleCreate(
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("10"))],
                payment_lines=[
                    SalePaymentLineInput(method="cash", amount=Decimal("60")),
                    SalePaymentLineInput(method="card", amount=Decimal("40")),
                ],
            ),
        )
        assert sale.shift_id == shift.id

        closed = close_shift(database, get_shift(database, shift.id), closing_cash=Decimal("100060"))
        assert closed.expected_cash == Decimal("100060.00")  # 100000 + 60 cash, 40 card excluded
        assert closed.difference == Decimal("0.00")


def test_shift_reconciliation_no_double_count_between_sale_lines_and_standalone_settlement() -> None:
    """A customer sale's cash line (SalePaymentLine) and a later standalone
    balance settlement (CustomerPayment with no sale_id) must both count
    toward expected_cash, exactly once each — this is the trickiest part of
    the new accounting, since a customer sale's paid amount is recorded in
    both tables for two different reasons.
    """
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        product = _make_product(database)
        cashier = _make_cashier(database)
        customer = Customer(full_name="Tab Customer", credit_limit=Decimal("1000000"))
        database.add(customer)
        database.commit()
        database.refresh(customer)

        shift = open_shift(database, cashier_id=cashier.id, opening_cash=Decimal("0"))

        # total = 100 * 10 = 1000, split 400 cash / 300 card, 300 left on account.
        sale = process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("100"))],
                payment_lines=[
                    SalePaymentLineInput(method="cash", amount=Decimal("400")),
                    SalePaymentLineInput(method="card", amount=Decimal("300")),
                ],
            ),
        )
        assert sale.remaining_amount == Decimal("300.00")

        # Customer later walks in and settles part of the remaining balance
        # in cash — not tied to this (or any) specific sale.
        record_customer_payment(
            database, customer, PaymentCreate(amount=Decimal("200"), method="cash")
        )

        closed = close_shift(database, get_shift(database, shift.id), closing_cash=Decimal("600"))
        # 0 opening + 400 (sale's cash line) + 200 (standalone settlement) = 600.
        # NOT 400 + 300 (card) and NOT double-counting the 400 a second time
        # through the old CustomerPayment-based path.
        assert closed.expected_cash == Decimal("600.00")
        assert closed.difference == Decimal("0.00")
