"""Cash paid OUT of the till during a shift must reduce expected cash.

Before this was handled, settling a supplier, the rent or a wage in cash
mid-shift produced a "shortage" at close of exactly that amount: the money
had genuinely left the drawer, but the expected figure still assumed it was
there. The arithmetic below is worked out by hand in the comments so the
assertion is checkable by eye, not just by running it.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.entities import (
    Category,
    Expense,
    ExpensePaymentMethod,
    PaymentMethod,
    Product,
    SalaryPayment,
    Supplier,
    SupplierPayment,
    User,
)
from app.schemas.sale import SaleCreate, SaleItemCreate, SalePaymentLineInput
from app.services.sales import process_sale
from app.services.shifts import close_shift, open_shift


def _setup(database: Session) -> tuple[User, Product]:
    cashier = User(username="c", password_hash="x", full_name="صندوق‌دار", role="cashier")
    database.add(cashier)
    category = Category(name="cat", description="d")
    database.add(category)
    database.flush()
    product = Product(
        barcode="1",
        name="کالا",
        category=category,
        purchase_price=Decimal("1000"),
        sale_price=Decimal("2000"),
        stock_quantity=Decimal("500"),
        low_stock_threshold=Decimal("1"),
        is_active=True,
    )
    database.add(product)
    database.commit()
    return cashier, product


def _cash_sale(database: Session, product: Product, shift_id: int, qty: int, invoice: str) -> Decimal:
    total = Decimal("2000") * qty
    sale = process_sale(
        database,
        SaleCreate(
            invoice_number=invoice,
            items=[SaleItemCreate(product_id=product.id, quantity=Decimal(qty))],
            payment_lines=[SalePaymentLineInput(method="cash", amount=total)],
        ),
    )
    sale.shift_id = shift_id
    database.commit()
    return total


def test_cash_paid_out_during_shift_reduces_expected_cash() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        cashier, product = _setup(database)
        supplier = Supplier(name="تأمین‌کننده", phone="021", credit_limit=Decimal("999999999"),
                            balance=Decimal("5000000"), is_active=True)
        database.add(supplier)
        database.commit()

        shift = open_shift(database, cashier_id=cashier.id, opening_cash=Decimal("1000000"))

        # IN: 20 units x 2,000 = 40,000 cash through the till
        cash_in = _cash_sale(database, product, shift.id, 20, "S-1")
        assert cash_in == Decimal("40000")

        now = datetime.now(UTC)
        # OUT: supplier settled in cash from the drawer
        database.add(SupplierPayment(supplier_id=supplier.id, amount=Decimal("30000"),
                                     method=PaymentMethod.CASH, paid_at=now))
        # OUT: a cash expense (e.g. a repair paid on the spot)
        database.add(Expense(category="تعمیرات", amount=Decimal("12000"), date=date.today(),
                             payment_method=ExpensePaymentMethod.CASH, created_at=now))
        # OUT: a wage advance handed over in cash
        database.add(SalaryPayment(employee_id=cashier.id, period_year=1405, period_month=5,
                                   base_amount=Decimal("8000"), bonus_amount=Decimal("0"),
                                   deductions_amount=Decimal("0"), net_amount=Decimal("8000"),
                                   payment_method=ExpensePaymentMethod.CASH, paid_at=now))
        # NOT cash, must be ignored on the way out
        database.add(Expense(category="اجاره", amount=Decimal("9_000_000"), date=date.today(),
                             payment_method=ExpensePaymentMethod.BANK, created_at=now))
        database.commit()

        # By hand:
        #   opening              1,000,000
        # + cash sales              40,000
        # - supplier (cash)         30,000
        # - expense  (cash)         12,000
        # - salary   (cash)          8,000
        #   (bank expense of 9,000,000 ignored: never in the drawer)
        #   ------------------------------
        #   expected               990,000
        expected = Decimal("990000")

        # A physical count of exactly that must show no discrepancy.
        closed = close_shift(database, shift, closing_cash=expected)

        assert closed.expected_cash == expected, closed.expected_cash
        assert closed.difference == Decimal("0"), closed.difference


def test_non_cash_tenders_never_enter_expected_cash() -> None:
    """card and card_to_card sales must not inflate the till."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        cashier, product = _setup(database)
        shift = open_shift(database, cashier_id=cashier.id, opening_cash=Decimal("500000"))

        for method, invoice in (("card", "S-CARD"), ("card_to_card", "S-C2C")):
            sale = process_sale(
                database,
                SaleCreate(
                    invoice_number=invoice,
                    items=[SaleItemCreate(product_id=product.id, quantity=Decimal("5"))],
                    payment_lines=[SalePaymentLineInput(method=method, amount=Decimal("10000"))],
                ),
            )
            sale.shift_id = shift.id
        database.commit()

        # Neither tender touches the drawer, so expected stays at the float.
        closed = close_shift(database, shift, closing_cash=Decimal("500000"))
        assert closed.expected_cash == Decimal("500000"), closed.expected_cash
        assert closed.difference == Decimal("0"), closed.difference
