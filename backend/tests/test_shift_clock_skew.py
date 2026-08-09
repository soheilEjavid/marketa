"""The till reconciliation must not depend on the wall clock behaving.

A shift's cash-out window used to be `opened_at <= t <= closed_at`, with
`closed_at` read from the wall clock at the moment of closing. Wall clocks
move backwards — NTP disciplines them, a VM resumes from suspend, WSL
resyncs with its host — and when one did, every row recorded during the
shift sorted after `closed_at` and dropped out. Observed in practice: a
shift opened at 12:43:51 closed at 12:41:51 and 50,000 of cash paid over
the counter simply vanished, showing the drawer richer than it was.

The window is now one-sided: everything from `opened_at` onward. These pin
that down across the boundaries, not just the case that was caught.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.entities import (
    CashierShift,
    CustomerPayment,
    Customer,
    Expense,
    ExpensePaymentMethod,
    PaymentMethod,
    Product,
    SalaryPayment,
    ShiftStatus,
    Supplier,
    SupplierPayment,
    User,
)
from app.schemas.sale import SaleCreate, SaleItemCreate, SalePaymentLineInput
from app.services import shifts as shifts_service
from app.services.sales import process_sale
from app.services.shifts import close_shift, get_shift, open_shift


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def _fixtures(database: Session) -> tuple[User, Product, Supplier]:
    cashier = User(username="c", password_hash="x", full_name="صندوق‌دار", role="cashier")
    product = Product(
        name="کالا", purchase_price=Decimal("1000"), sale_price=Decimal("2000"),
        stock_quantity=Decimal("1000"), low_stock_threshold=Decimal("0"), is_active=True,
    )
    supplier = Supplier(name="تأمین‌کننده", balance=Decimal("9999999"), is_active=True)
    database.add_all([cashier, product, supplier])
    database.commit()
    return cashier, product, supplier


def _open_at(database: Session, cashier: User, opened_at: datetime, opening_cash: str) -> CashierShift:
    """A shift whose opened_at we control, so a test can place rows either
    side of it without racing a real clock."""
    shift = open_shift(database, cashier_id=cashier.id, opening_cash=Decimal(opening_cash))
    shift.opened_at = opened_at
    database.commit()
    return shift


def _cash_out(database: Session, supplier: Supplier, cashier: User, moment: datetime) -> None:
    """30,000 + 12,000 + 8,000 = 50,000 of cash leaving the drawer."""
    database.add(SupplierPayment(supplier_id=supplier.id, amount=Decimal("30000"),
                                 method=PaymentMethod.CASH, paid_at=moment))
    database.add(Expense(category="تعمیرات", amount=Decimal("12000"), date=date.today(),
                         payment_method=ExpensePaymentMethod.CASH, created_at=moment))
    database.add(SalaryPayment(employee_id=cashier.id, period_year=1405, period_month=5,
                               base_amount=Decimal("8000"), bonus_amount=Decimal("0"),
                               deductions_amount=Decimal("0"), net_amount=Decimal("8000"),
                               payment_method=ExpensePaymentMethod.CASH, paid_at=moment))
    database.commit()


def _freeze_close(monkeypatch, moment: datetime) -> None:
    """Pin the clock close_shift reads, so a backwards jump is deterministic."""
    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment
    monkeypatch.setattr(shifts_service, "datetime", _Clock)


# ── The bug that was caught ──────────────────────────────────────────────

def test_cash_out_survives_the_clock_being_set_backwards(monkeypatch) -> None:
    with _session() as database:
        cashier, product, supplier = _fixtures(database)
        opened = datetime(2026, 8, 9, 12, 43, 51, tzinfo=UTC)
        shift = _open_at(database, cashier, opened, "1000000")

        process_sale(database, SaleCreate(
            invoice_number="S-1",
            items=[SaleItemCreate(product_id=product.id, quantity=Decimal("20"))],
            payment_lines=[SalePaymentLineInput(method="cash", amount=Decimal("40000"))]))
        _cash_out(database, supplier, cashier, opened + timedelta(seconds=1))

        # The clock is corrected two minutes backwards before the till is counted.
        _freeze_close(monkeypatch, opened - timedelta(minutes=2))
        closed = close_shift(database, get_shift(database, shift.id), closing_cash=Decimal("990000"))

        # 1,000,000 float + 40,000 taken − 50,000 paid out.
        assert closed.expected_cash == Decimal("990000.00")
        assert closed.difference == Decimal("0.00")
        assert closed.closed_at >= closed.opened_at, "a shift cannot close before it opened"


@pytest.mark.parametrize("clock_reads_minutes_from_open", [-120, -5, -1, 0, 1, 60])
def test_the_reconciliation_is_the_same_whatever_the_clock_reads_at_close(
    monkeypatch, clock_reads_minutes_from_open
) -> None:
    """The cash-out rows sit 30 seconds into the shift. This sweeps what the
    clock happens to read when the till is counted — from two hours behind
    that moment to an hour ahead. The last two are the ordinary case; the
    rest are what a corrected clock produces, and each one used to swallow
    the whole 50,000."""
    with _session() as database:
        cashier, product, supplier = _fixtures(database)
        opened = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
        shift = _open_at(database, cashier, opened, "1000000")

        process_sale(database, SaleCreate(
            invoice_number="S-1",
            items=[SaleItemCreate(product_id=product.id, quantity=Decimal("20"))],
            payment_lines=[SalePaymentLineInput(method="cash", amount=Decimal("40000"))]))
        _cash_out(database, supplier, cashier, opened + timedelta(seconds=30))

        _freeze_close(monkeypatch, opened + timedelta(minutes=clock_reads_minutes_from_open))
        closed = close_shift(database, get_shift(database, shift.id), closing_cash=Decimal("990000"))
        assert closed.expected_cash == Decimal("990000.00")


# ── The boundaries themselves ────────────────────────────────────────────

def test_cash_out_in_the_very_second_the_shift_opened_counts() -> None:
    with _session() as database:
        cashier, _, supplier = _fixtures(database)
        opened = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
        shift = _open_at(database, cashier, opened, "1000000")
        _cash_out(database, supplier, cashier, opened)

        closed = close_shift(database, get_shift(database, shift.id), closing_cash=Decimal("950000"))
        assert closed.expected_cash == Decimal("950000.00")


def test_cash_out_from_before_the_shift_opened_is_not_counted() -> None:
    with _session() as database:
        cashier, _, supplier = _fixtures(database)
        opened = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
        shift = _open_at(database, cashier, opened, "1000000")
        # A second earlier — the previous shift's business.
        _cash_out(database, supplier, cashier, opened - timedelta(seconds=1))

        closed = close_shift(database, get_shift(database, shift.id), closing_cash=Decimal("1000000"))
        assert closed.expected_cash == Decimal("1000000.00")


def test_two_shifts_in_one_day_do_not_share_the_same_cash_out() -> None:
    """The classic double-count: without a lower bound keyed to each shift,
    the same expense is deducted twice and the second till reads short."""
    with _session() as database:
        cashier, _, supplier = _fixtures(database)

        first = _open_at(database, cashier, datetime(2026, 8, 9, 8, 0, 0, tzinfo=UTC), "1000000")
        _cash_out(database, supplier, cashier, datetime(2026, 8, 9, 9, 0, 0, tzinfo=UTC))
        closed_first = close_shift(database, get_shift(database, first.id), closing_cash=Decimal("950000"))
        assert closed_first.expected_cash == Decimal("950000.00")

        second = _open_at(database, cashier, datetime(2026, 8, 9, 16, 0, 0, tzinfo=UTC), "500000")
        closed_second = close_shift(database, get_shift(database, second.id), closing_cash=Decimal("500000"))
        assert closed_second.expected_cash == Decimal("500000.00"), (
            "the morning's expense must not be deducted from the evening till too"
        )


def test_a_standalone_cash_settlement_still_counts_in() -> None:
    with _session() as database:
        cashier, _, _ = _fixtures(database)
        customer = Customer(full_name="مشتری", balance=Decimal("300000"), credit_limit=Decimal("0"))
        database.add(customer)
        database.commit()

        opened = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
        shift = _open_at(database, cashier, opened, "0")
        database.add(CustomerPayment(customer_id=customer.id, sale_id=None, amount=Decimal("200000"),
                                     method=PaymentMethod.CASH, paid_at=opened + timedelta(minutes=5)))
        database.commit()

        closed = close_shift(database, get_shift(database, shift.id), closing_cash=Decimal("200000"))
        assert closed.expected_cash == Decimal("200000.00")


def test_non_cash_movements_are_still_ignored_on_both_sides() -> None:
    with _session() as database:
        cashier, product, supplier = _fixtures(database)
        opened = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
        shift = _open_at(database, cashier, opened, "0")

        process_sale(database, SaleCreate(
            invoice_number="S-1",
            items=[SaleItemCreate(product_id=product.id, quantity=Decimal("20"))],
            payment_lines=[SalePaymentLineInput(method="card", amount=Decimal("40000"))]))
        database.add(SupplierPayment(supplier_id=supplier.id, amount=Decimal("30000"),
                                     method=PaymentMethod.CARD, paid_at=opened + timedelta(minutes=1)))
        database.add(Expense(category="اجاره", amount=Decimal("9000000"), date=date.today(),
                             payment_method=ExpensePaymentMethod.BANK, created_at=opened + timedelta(minutes=2)))
        database.commit()

        closed = close_shift(database, get_shift(database, shift.id), closing_cash=Decimal("0"))
        assert closed.expected_cash == Decimal("0.00"), "nothing here went through the drawer"


def test_a_closed_shift_keeps_the_figure_it_was_closed_with(monkeypatch) -> None:
    """Closing is a one-time reckoning: a later shift's activity must never
    reach back and change a till that has already been counted."""
    with _session() as database:
        cashier, _, supplier = _fixtures(database)
        opened = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
        shift = _open_at(database, cashier, opened, "1000000")
        _cash_out(database, supplier, cashier, opened + timedelta(minutes=1))

        closed = close_shift(database, get_shift(database, shift.id), closing_cash=Decimal("950000"))
        stored = closed.expected_cash
        assert stored == Decimal("950000.00")

        # More cash goes out afterwards, under the next shift.
        database.add(SupplierPayment(supplier_id=supplier.id, amount=Decimal("77000"),
                                     method=PaymentMethod.CASH, paid_at=opened + timedelta(hours=9)))
        database.commit()
        database.refresh(closed)
        assert closed.expected_cash == stored
        assert closed.status == ShiftStatus.CLOSED
