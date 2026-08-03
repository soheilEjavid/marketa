from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Expense, SalaryAdvance, SalaryPayment, User
from app.schemas.expense import (
    ExpenseCreate,
    ExpenseUpdate,
    SalaryAdvanceCreate,
    SalaryPaymentCreate,
    SalaryPaymentUpdate,
)


class ExpenseError(ValueError):
    pass


class EmployeeNotFoundError(ExpenseError):
    pass


class DuplicateSalaryPaymentError(ExpenseError):
    """Raised when a payment already exists for this employee/period —
    surfaced as a clean 409 instead of letting the DB's unique constraint
    (uq_salary_payments_employee_period) bubble up as a raw IntegrityError.
    """


def _get_active_employee(database: Session, employee_id: int) -> User:
    employee = database.get(User, employee_id)
    if employee is None or not employee.is_active:
        raise EmployeeNotFoundError("Employee not found or inactive")
    return employee


# ─────────────────────────────────────────────────────────────────────────
# Expense (general/fixed operating expenses)
# ─────────────────────────────────────────────────────────────────────────

def create_expense(database: Session, data: ExpenseCreate, *, created_by_user_id: int | None) -> Expense:
    expense = Expense(
        category=data.category,
        amount=data.amount,
        date=data.date,
        description=data.description,
        is_recurring=data.is_recurring,
        payment_method=data.payment_method,
        receipt_image_url=data.receipt_image_url,
        created_by_user_id=created_by_user_id,
    )
    database.add(expense)
    database.commit()
    database.refresh(expense)
    return expense


def update_expense(database: Session, expense: Expense, data: ExpenseUpdate) -> Expense:
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(expense, field, value)
    database.commit()
    database.refresh(expense)
    return expense


def get_expense(database: Session, expense_id: int) -> Expense | None:
    return database.get(Expense, expense_id)


def list_expenses(
    database: Session, *, from_date: date | None = None, to_date: date | None = None
) -> list[Expense]:
    query = select(Expense).order_by(Expense.date.desc(), Expense.id.desc())
    if from_date:
        query = query.where(Expense.date >= from_date)
    if to_date:
        query = query.where(Expense.date <= to_date)
    return list(database.scalars(query).all())


def distinct_expense_categories(database: Session) -> list[str]:
    """Backs the frontend's <datalist> autocomplete — every distinct
    category value used so far, so the field feels "managed" without a
    real category table (see docs/expense-management.md / entities.py's
    Expense docstring for why this isn't a foreign key)."""
    rows = database.execute(select(Expense.category).distinct().order_by(Expense.category)).all()
    return [row[0] for row in rows]


# ─────────────────────────────────────────────────────────────────────────
# Salary advances (مساعده)
# ─────────────────────────────────────────────────────────────────────────

def create_salary_advance(database: Session, data: SalaryAdvanceCreate) -> SalaryAdvance:
    _get_active_employee(database, data.employee_id)
    advance = SalaryAdvance(
        employee_id=data.employee_id,
        amount=data.amount,
        date=data.date,
        notes=data.notes,
    )
    database.add(advance)
    database.commit()
    database.refresh(advance)
    return advance


def list_salary_advances(database: Session, *, employee_id: int | None = None) -> list[SalaryAdvance]:
    query = select(SalaryAdvance).order_by(SalaryAdvance.date.desc(), SalaryAdvance.id.desc())
    if employee_id is not None:
        query = query.where(SalaryAdvance.employee_id == employee_id)
    return list(database.scalars(query).all())


def _unsettled_advances(database: Session, employee_id: int) -> list[SalaryAdvance]:
    return list(
        database.scalars(
            select(SalaryAdvance).where(
                SalaryAdvance.employee_id == employee_id,
                SalaryAdvance.settled_in_payment_id.is_(None),
            )
        ).all()
    )


# ─────────────────────────────────────────────────────────────────────────
# Salary payments (حقوق و دستمزد)
# ─────────────────────────────────────────────────────────────────────────

def create_salary_payment(database: Session, data: SalaryPaymentCreate, *, created_by_user_id: int | None) -> SalaryPayment:
    _get_active_employee(database, data.employee_id)

    existing = database.scalar(
        select(SalaryPayment).where(
            SalaryPayment.employee_id == data.employee_id,
            SalaryPayment.period_year == data.period_year,
            SalaryPayment.period_month == data.period_month,
        )
    )
    if existing is not None:
        raise DuplicateSalaryPaymentError(
            f"A salary payment for employee {data.employee_id} in {data.period_year}/{data.period_month} already exists"
        )

    # Every currently-unsettled advance for this employee is swept into this
    # payment automatically, regardless of which month it was taken in —
    # deliberately more permissive than "only this same month's advances" so
    # an advance never sits forgotten just because it crossed a month
    # boundary before a payment was created (see docs/expense-management.md).
    advances = _unsettled_advances(database, data.employee_id)
    advance_total = sum((advance.amount for advance in advances), Decimal("0"))
    deductions_amount = data.other_deductions_amount + advance_total
    net_amount = data.base_amount + data.bonus_amount - deductions_amount

    payment = SalaryPayment(
        employee_id=data.employee_id,
        period_year=data.period_year,
        period_month=data.period_month,
        base_amount=data.base_amount,
        bonus_amount=data.bonus_amount,
        deductions_amount=deductions_amount,
        net_amount=net_amount,
        payment_method=data.payment_method,
        notes=data.notes,
        created_by_user_id=created_by_user_id,
    )
    database.add(payment)
    database.flush()

    for advance in advances:
        advance.settled_in_payment_id = payment.id

    database.commit()
    database.refresh(payment)
    return payment


def update_salary_payment(database: Session, payment: SalaryPayment, data: SalaryPaymentUpdate) -> SalaryPayment:
    """Only base/bonus/other-deductions/method/notes are editable — the
    advance portion already folded into deductions_amount at creation time
    is not reopened here (the settled advances keep their
    settled_in_payment_id pointing at this payment either way)."""
    updates = data.model_dump(exclude_unset=True)
    other_deductions = updates.pop("other_deductions_amount", None)

    for field, value in updates.items():
        setattr(payment, field, value)

    if other_deductions is not None:
        advance_total = _settled_advance_total(database, payment)
        payment.deductions_amount = other_deductions + advance_total

    payment.net_amount = payment.base_amount + payment.bonus_amount - payment.deductions_amount
    database.commit()
    database.refresh(payment)
    return payment


def _settled_advance_total(database: Session, payment: SalaryPayment) -> Decimal:
    """The advance-only portion of an existing payment's deductions_amount —
    recovered by summing the advances actually settled against it, since
    other_deductions_amount itself isn't stored as its own column (only the
    combined deductions_amount is, matching the doc's SalaryPayment shape)."""
    rows = database.execute(
        select(SalaryAdvance.amount).where(SalaryAdvance.settled_in_payment_id == payment.id)
    ).all()
    return sum((row[0] for row in rows), Decimal("0"))


def get_salary_payment(database: Session, payment_id: int) -> SalaryPayment | None:
    return database.get(SalaryPayment, payment_id)


def list_salary_payments(
    database: Session, *, employee_id: int | None = None
) -> list[SalaryPayment]:
    query = select(SalaryPayment).order_by(
        SalaryPayment.period_year.desc(), SalaryPayment.period_month.desc(), SalaryPayment.id.desc()
    )
    if employee_id is not None:
        query = query.where(SalaryPayment.employee_id == employee_id)
    return list(database.scalars(query).all())


def to_salary_payment_read(payment: SalaryPayment) -> dict:
    return {
        "id": payment.id,
        "employee_id": payment.employee_id,
        "employee_name": payment.employee.full_name,
        "period_year": payment.period_year,
        "period_month": payment.period_month,
        "base_amount": payment.base_amount,
        "bonus_amount": payment.bonus_amount,
        "deductions_amount": payment.deductions_amount,
        "net_amount": payment.net_amount,
        "payment_method": payment.payment_method,
        "paid_at": payment.paid_at,
        "notes": payment.notes,
        "created_by_user_id": payment.created_by_user_id,
    }


def to_salary_advance_read(advance: SalaryAdvance) -> dict:
    return {
        "id": advance.id,
        "employee_id": advance.employee_id,
        "employee_name": advance.employee.full_name,
        "amount": advance.amount,
        "date": advance.date,
        "notes": advance.notes,
        "settled_in_payment_id": advance.settled_in_payment_id,
    }


# ─────────────────────────────────────────────────────────────────────────
# Combined operating-expense total (feeds services/reports.py::net_profit)
# ─────────────────────────────────────────────────────────────────────────

def total_operating_expenses(database: Session, period_start: date, period_end: date) -> Decimal:
    """Expense.date is used for general expenses; SalaryPayment.paid_at
    (the real cash-out moment) for salaries — matching how every other
    period-based report in this app (CustomerPayment/SupplierPayment) uses
    the actual payment timestamp, not an accrual date."""
    expense_rows = database.execute(
        select(Expense.amount).where(Expense.date >= period_start, Expense.date <= period_end)
    ).all()
    expense_sum = sum((row[0] for row in expense_rows), Decimal("0"))

    salary_rows = database.execute(
        select(SalaryPayment.net_amount).where(
            func.date(SalaryPayment.paid_at) >= period_start,
            func.date(SalaryPayment.paid_at) <= period_end,
        )
    ).all()
    salary_sum = sum((row[0] for row in salary_rows), Decimal("0"))

    return expense_sum + salary_sum
