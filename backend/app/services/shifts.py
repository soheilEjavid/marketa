from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    CashierShift,
    CustomerPayment,
    DocumentStatus,
    Expense,
    ExpensePaymentMethod,
    PaymentMethod,
    SalaryPayment,
    Sale,
    SalePaymentLine,
    ShiftStatus,
    SupplierPayment,
    User,
)


class ShiftError(ValueError):
    pass


def get_open_shift(database: Session) -> CashierShift | None:
    return database.scalar(select(CashierShift).where(CashierShift.status == ShiftStatus.OPEN))


def open_shift(database: Session, *, cashier_id: int, opening_cash: Decimal) -> CashierShift:
    if get_open_shift(database) is not None:
        raise ShiftError("A shift is already open — close it before opening another")
    cashier = database.get(User, cashier_id)
    if cashier is None or not cashier.is_active:
        raise ShiftError("Cashier not found or inactive")

    shift = CashierShift(cashier_id=cashier_id, opening_cash=opening_cash, status=ShiftStatus.OPEN)
    database.add(shift)
    database.commit()
    database.refresh(shift)
    return shift


def close_shift(
    database: Session, shift: CashierShift, *, closing_cash: Decimal, notes: str | None = None
) -> CashierShift:
    """Reconcile counted cash against expected cash for this shift.

    expected_cash = opening float + the cash portion of every sale's
    payment lines (SalePaymentLine — walk-in or customer-linked, single or
    split-payment, doesn't matter) attached to this shift, plus cash
    CustomerPayment rows not tied to any sale (e.g. a customer settling part
    of their balance later, in cash, via POST /customers/{id}/payments).
    The sale_id.is_(None) filter on the CustomerPayment sum is what avoids
    double-counting: a customer sale's initial cash tender is now counted
    through SalePaymentLine instead. Split payments resolve the previous
    version's documented gap (an immediate cash top-up on an otherwise
    credit sale is now a real, attributable payment line, not something
    silently invisible to this reconciliation).

    Cash paid OUT during the shift is then subtracted: cash SupplierPayment
    rows, cash Expense rows and cash SalaryPayment rows. Card, bank and
    card-to-card movements are all deliberately ignored on both sides —
    none of them passes through the drawer.
    """
    if shift.status != ShiftStatus.OPEN:
        raise ShiftError("Shift is already closed")

    closed_at = datetime.now(UTC)

    cash_sales_total = database.scalar(
        select(func.coalesce(func.sum(SalePaymentLine.amount), 0))
        .select_from(SalePaymentLine)
        .join(Sale, Sale.id == SalePaymentLine.sale_id)
        .where(
            Sale.shift_id == shift.id,
            Sale.status == DocumentStatus.COMPLETED,
            SalePaymentLine.method == PaymentMethod.CASH,
        )
    ) or Decimal("0")

    # SQLite stores DateTime columns as plain TEXT and compares them
    # lexicographically. server_default=func.now() rows (opened_at) render
    # without a fractional-seconds suffix, but a Python datetime re-bound as
    # a query parameter is formatted WITH one (".000000") — so a naive
    # `paid_at >= shift.opened_at` silently drops rows from the same
    # instant the shift opened. Wrapping both sides in func.datetime(...)
    # normalizes them to the same canonical string before comparing.
    cash_customer_payments = database.scalar(
        select(func.coalesce(func.sum(CustomerPayment.amount), 0)).where(
            CustomerPayment.method == PaymentMethod.CASH,
            CustomerPayment.sale_id.is_(None),
            func.datetime(CustomerPayment.paid_at) >= func.datetime(shift.opened_at),
            func.datetime(CustomerPayment.paid_at) <= func.datetime(closed_at),
        )
    ) or Decimal("0")

    # Cash paid OUT of the till during the shift. Until this was added, a
    # manager settling a supplier, the rent or a wage in cash mid-shift
    # produced a "shortage" of exactly that amount at close — the money was
    # genuinely gone from the drawer, but the expected figure still assumed
    # it was there. That is the single most alarming number this app can
    # show a shopkeeper, and it was routine, not an edge case.
    #
    # All three sources are matched on a real timestamp, not on a calendar
    # date. Expense carries a business `date` (day granularity), but two
    # shifts can run in one day and a day-based match would then deduct the
    # same expense from both, turning one phantom shortage into a phantom
    # overage. `created_at` is when the row was actually entered, which is
    # the moment the cash left the drawer for a shopkeeper recording as they
    # go. The trade-off: an expense back-dated days later is attributed to
    # the shift it was *entered* in. That is visible and correctable;
    # silently double-counting would not be.
    cash_out_conditions = lambda column: (  # noqa: E731 - local shorthand
        func.datetime(column) >= func.datetime(shift.opened_at),
        func.datetime(column) <= func.datetime(closed_at),
    )

    cash_supplier_payments = database.scalar(
        select(func.coalesce(func.sum(SupplierPayment.amount), 0)).where(
            SupplierPayment.method == PaymentMethod.CASH,
            *cash_out_conditions(SupplierPayment.paid_at),
        )
    ) or Decimal("0")

    cash_expenses = database.scalar(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.payment_method == ExpensePaymentMethod.CASH,
            *cash_out_conditions(Expense.created_at),
        )
    ) or Decimal("0")

    cash_salaries = database.scalar(
        select(func.coalesce(func.sum(SalaryPayment.net_amount), 0)).where(
            SalaryPayment.payment_method == ExpensePaymentMethod.CASH,
            *cash_out_conditions(SalaryPayment.paid_at),
        )
    ) or Decimal("0")

    cash_out_total = cash_supplier_payments + cash_expenses + cash_salaries

    expected_cash = (
        shift.opening_cash + cash_sales_total + cash_customer_payments - cash_out_total
    )

    shift.closing_cash = closing_cash
    shift.expected_cash = expected_cash
    shift.difference = closing_cash - expected_cash
    shift.status = ShiftStatus.CLOSED
    shift.closed_at = closed_at
    shift.notes = notes

    database.commit()
    database.refresh(shift)
    return shift


def list_shifts(database: Session) -> list[CashierShift]:
    return list(
        database.scalars(
            select(CashierShift)
            .options(selectinload(CashierShift.cashier))
            .order_by(CashierShift.opened_at.desc())
        )
    )


def get_shift(database: Session, shift_id: int) -> CashierShift | None:
    return database.scalar(
        select(CashierShift)
        .where(CashierShift.id == shift_id)
        .options(selectinload(CashierShift.cashier), selectinload(CashierShift.sales))
    )


def to_shift_read(shift: CashierShift) -> dict:
    return {
        "id": shift.id,
        "cashier_id": shift.cashier_id,
        "cashier_name": shift.cashier.full_name if shift.cashier else "—",
        "status": shift.status,
        "opening_cash": shift.opening_cash,
        "closing_cash": shift.closing_cash,
        "expected_cash": shift.expected_cash,
        "difference": shift.difference,
        "opened_at": shift.opened_at,
        "closed_at": shift.closed_at,
        "notes": shift.notes,
    }
