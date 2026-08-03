from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.entities import DocumentStatus, Expense, ExpensePaymentMethod, PaymentMethod, Sale, SaleItem, User
from app.schemas.expense import ExpenseCreate, SalaryAdvanceCreate, SalaryPaymentCreate
from app.services.expenses import (
    DuplicateSalaryPaymentError,
    EmployeeNotFoundError,
    create_expense,
    create_salary_advance,
    create_salary_payment,
)
from app.services.reports import net_profit


def _make_employee(database: Session, username: str = "cashier1") -> User:
    employee = User(username=username, password_hash="x", full_name="Employee One", role="cashier", is_active=True)
    database.add(employee)
    database.commit()
    database.refresh(employee)
    return employee


def _make_sale(database: Session, *, quantity: str, unit_price: str, cost_price: str, when: datetime) -> None:
    qty, price, cost = Decimal(quantity), Decimal(unit_price), Decimal(cost_price)
    revenue = qty * price
    sale = Sale(
        invoice_number=f"EXP-{when.isoformat()}",
        status=DocumentStatus.COMPLETED,
        payment_method=PaymentMethod.CASH,
        subtotal=revenue,
        total=revenue,
        created_at=when,
    )
    database.add(sale)
    database.flush()
    database.add(
        SaleItem(
            sale_id=sale.id,
            product_id=1,  # no Product row needed — daily_sales_summary never joins Product
            quantity=qty,
            unit_price=price,
            cost_price=cost,
            discount=Decimal("0"),
            line_total=revenue,
        )
    )
    database.commit()


def test_net_profit_matches_hand_calculation() -> None:
    """
    HAND CALCULATION:

    Gross profit: one sale in June — qty=10, unit_price=100, cost_price=60.
      line_total = 10 * 100 = 1000
      profit = line_total - (cost_price * quantity) = 1000 - (60 * 10) = 400
      -> gross_profit = 400

    Operating expenses in June:
      Expense: amount = 100 (date = 2026-06-15)
      SalaryPayment: base=500, bonus=50, deductions=30
        -> net_amount = 500 + 50 - 30 = 520 (paid_at = 2026-06-20)
      -> total_operating_expenses = 100 + 520 = 620

    net_profit = gross_profit - total_operating_expenses = 400 - 620 = -220
    (a genuine net LOSS despite positive gross profit — exactly the gap
    this feature exists to reveal.)
    """
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        employee = _make_employee(database)

        _make_sale(
            database,
            quantity="10",
            unit_price="100",
            cost_price="60",
            when=datetime(2026, 6, 10, tzinfo=UTC),
        )

        create_expense(
            database,
            ExpenseCreate(
                category="اجاره",
                amount=Decimal("100"),
                date=date(2026, 6, 15),
                payment_method=ExpensePaymentMethod.BANK,
            ),
            created_by_user_id=None,
        )

        payment = create_salary_payment(
            database,
            SalaryPaymentCreate(
                employee_id=employee.id,
                period_year=1405,
                period_month=6,
                base_amount=Decimal("500"),
                bonus_amount=Decimal("50"),
                other_deductions_amount=Decimal("30"),
                payment_method=ExpensePaymentMethod.CASH,
            ),
            created_by_user_id=None,
        )
        payment.paid_at = datetime(2026, 6, 20, tzinfo=UTC)
        database.commit()

        assert payment.net_amount == Decimal("520")

        report = net_profit(database, date(2026, 6, 1), date(2026, 6, 30))
        assert report["gross_profit"] == Decimal("400")
        assert report["total_operating_expenses"] == Decimal("620")
        assert report["net_profit"] == Decimal("-220")


def test_salary_advance_folds_into_same_month_payment() -> None:
    """A mid-month advance must automatically become part of that month's
    salary payment's deductions_amount, with settled_in_payment_id set —
    not a free-typed number the manager has to remember to enter."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        employee = _make_employee(database)

        advance = create_salary_advance(
            database,
            SalaryAdvanceCreate(employee_id=employee.id, amount=Decimal("200"), date=date(2026, 6, 12)),
        )
        assert advance.settled_in_payment_id is None

        payment = create_salary_payment(
            database,
            SalaryPaymentCreate(
                employee_id=employee.id,
                period_year=1405,
                period_month=6,
                base_amount=Decimal("1000"),
                bonus_amount=Decimal("0"),
                other_deductions_amount=Decimal("50"),
                payment_method=ExpensePaymentMethod.CASH,
            ),
            created_by_user_id=None,
        )

        # deductions = other_deductions(50) + folded advance(200) = 250
        assert payment.deductions_amount == Decimal("250")
        # net = base(1000) + bonus(0) - deductions(250) = 750
        assert payment.net_amount == Decimal("750")

        database.refresh(advance)
        assert advance.settled_in_payment_id == payment.id


def test_duplicate_salary_payment_for_same_period_rejected() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        employee = _make_employee(database)
        create_salary_payment(
            database,
            SalaryPaymentCreate(
                employee_id=employee.id,
                period_year=1405,
                period_month=6,
                base_amount=Decimal("1000"),
                payment_method=ExpensePaymentMethod.CASH,
            ),
            created_by_user_id=None,
        )

        with pytest.raises(DuplicateSalaryPaymentError):
            create_salary_payment(
                database,
                SalaryPaymentCreate(
                    employee_id=employee.id,
                    period_year=1405,
                    period_month=6,
                    base_amount=Decimal("1000"),
                    payment_method=ExpensePaymentMethod.CASH,
                ),
                created_by_user_id=None,
            )


def test_salary_payment_rejects_unknown_employee() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        with pytest.raises(EmployeeNotFoundError):
            create_salary_payment(
                database,
                SalaryPaymentCreate(
                    employee_id=999,
                    period_year=1405,
                    period_month=6,
                    base_amount=Decimal("1000"),
                    payment_method=ExpensePaymentMethod.CASH,
                ),
                created_by_user_id=None,
            )
