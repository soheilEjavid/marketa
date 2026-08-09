"""Returning goods has to reverse the money, not just the stock.

Before these, a return put the merchandise back on the shelf and left the
invoice untouched — the shop went on reporting revenue and profit on goods
standing in its own stockroom, the customer was never credited, and the
returned quantity was never checked against what had actually been sold.
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.entities import (
    Customer,
    CustomerPayment,
    DocumentStatus,
    PaymentMethod,
    Product,
    SalePaymentLine,
    Supplier,
    User,
)
from app.schemas.purchase import PurchaseCreate, PurchaseItemCreate
from app.schemas.sale import SaleCreate, SaleItemCreate, SalePaymentLineInput
from app.services.adjustments import AdjustmentError, adjust_stock, return_purchase_items, return_sale_items
from app.services.purchases import process_purchase
from app.services.reports import daily_sales_summary
from app.services.sales import process_sale
from app.services.shifts import close_shift, open_shift


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def _product(database: Session, *, stock: str = "10", cost: str = "60000", price: str = "100000") -> Product:
    product = Product(
        name="شیر پرچرب ۱ لیتری",
        purchase_price=Decimal(cost),
        sale_price=Decimal(price),
        stock_quantity=Decimal(stock),
        low_stock_threshold=Decimal("2"),
        is_active=True,
    )
    database.add(product)
    database.commit()
    database.refresh(product)
    return product


# ── Sale returns ─────────────────────────────────────────────────────────

def test_return_reverses_revenue_cost_and_refunds_a_paid_sale() -> None:
    with _session() as database:
        product = _product(database)
        sale = process_sale(
            database,
            SaleCreate(
                invoice_number="S-1",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("2"))],
                payment_lines=[SalePaymentLineInput(method="cash", amount=Decimal("200000"))],
            ),
        )
        assert sale.total == Decimal("200000.00")

        return_sale_items(database, sale.id, [{"product_id": product.id, "quantity": Decimal("1")}])
        database.refresh(sale)
        database.refresh(product)

        assert product.stock_quantity == Decimal("9.000")
        assert sale.total == Decimal("100000.00"), "revenue must drop with the goods"
        assert sale.paid_amount == Decimal("100000.00"), "half the money goes back"
        assert sale.remaining_amount == Decimal("0.00")

        # The refund is a real negative cash line, so the till and the
        # payment-method report both see the money leave.
        refunds = database.scalars(
            select(SalePaymentLine).where(SalePaymentLine.sale_id == sale.id, SalePaymentLine.amount < 0)
        ).all()
        assert len(refunds) == 1
        assert refunds[0].amount == Decimal("-100000.00")
        assert refunds[0].method == PaymentMethod.CASH


def test_returned_goods_stop_counting_toward_profit() -> None:
    with _session() as database:
        product = _product(database)
        sale = process_sale(
            database,
            SaleCreate(
                invoice_number="S-2",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("2"))],
                payment_lines=[SalePaymentLineInput(method="cash", amount=Decimal("200000"))],
            ),
        )

        rows = daily_sales_summary(database)
        assert sum(row["profit"] for row in rows) == Decimal("80000.00"), "2 × (100k − 60k)"

        return_sale_items(database, sale.id, [{"product_id": product.id, "quantity": Decimal("1")}])

        rows = daily_sales_summary(database)
        assert sum(row["total_sales"] for row in rows) == Decimal("100000.00")
        assert sum(row["profit"] for row in rows) == Decimal("40000.00"), "one unit's margin, not two"


def test_return_on_an_unpaid_credit_sale_clears_the_debt_without_a_refund() -> None:
    with _session() as database:
        product = _product(database)
        customer = Customer(full_name="مشتری", balance=Decimal("0"), credit_limit=Decimal("0"))
        database.add(customer)
        database.commit()

        sale = process_sale(
            database,
            SaleCreate(
                invoice_number="S-3",
                customer_id=customer.id,
                payment_method="credit",
                paid_amount=Decimal("0"),
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("2"))],
            ),
        )
        database.refresh(customer)
        assert customer.balance == Decimal("200000.00")

        return_sale_items(database, sale.id, [{"product_id": product.id, "quantity": Decimal("2")}])
        database.refresh(customer)
        database.refresh(sale)

        assert customer.balance == Decimal("0.00"), "they owe nothing for goods they gave back"
        assert sale.paid_amount == Decimal("0.00"), "no money moved, so none comes back"
        assert sale.status == DocumentStatus.CANCELLED, "nothing left on the invoice"
        assert database.scalars(
            select(SalePaymentLine).where(SalePaymentLine.sale_id == sale.id)
        ).all() == []


def test_return_credits_a_paying_customers_account_and_claws_back_points() -> None:
    with _session() as database:
        product = _product(database)
        customer = Customer(full_name="مشتری", balance=Decimal("0"), credit_limit=Decimal("0"), loyalty_member=True)
        database.add(customer)
        database.commit()

        sale = process_sale(
            database,
            SaleCreate(
                invoice_number="S-4",
                customer_id=customer.id,
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("4"))],
                payment_lines=[SalePaymentLineInput(method="cash", amount=Decimal("400000"))],
            ),
        )
        database.refresh(customer)
        points_before = customer.loyalty_points_balance
        assert points_before > 0, "the fixture needs the sale to have earned points"

        return_sale_items(database, sale.id, [{"product_id": product.id, "quantity": Decimal("2")}])
        database.refresh(customer)
        database.refresh(sale)

        assert sale.total == Decimal("200000.00")
        assert customer.balance == Decimal("0.00"), "paid in full, refunded in full — nothing owed either way"
        assert customer.loyalty_points_balance < points_before, "points earned on returned goods come back"
        assert customer.loyalty_points_balance >= 0

        # The customer ledger and the sale's paid_amount must stay in step.
        ledger_total = sum(
            payment.amount
            for payment in database.scalars(select(CustomerPayment).where(CustomerPayment.sale_id == sale.id))
        )
        assert ledger_total == sale.paid_amount


def test_partial_return_prorates_the_invoice_discount() -> None:
    with _session() as database:
        product = _product(database)
        sale = process_sale(
            database,
            SaleCreate(
                invoice_number="S-5",
                discount=Decimal("20000"),
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("4"))],
                payment_lines=[SalePaymentLineInput(method="cash", amount=Decimal("380000"))],
            ),
        )
        assert sale.total == Decimal("380000.00")

        return_sale_items(database, sale.id, [{"product_id": product.id, "quantity": Decimal("2")}])
        database.refresh(sale)

        assert sale.subtotal == Decimal("200000.00")
        assert sale.discount == Decimal("10000.00"), "half the basket left, half the discount left"
        assert sale.total == Decimal("190000.00")
        assert sale.paid_amount == Decimal("190000.00")


def test_cannot_return_more_than_was_sold_even_across_several_returns() -> None:
    with _session() as database:
        product = _product(database)
        sale = process_sale(
            database,
            SaleCreate(
                invoice_number="S-6",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("2"))],
                payment_lines=[SalePaymentLineInput(method="cash", amount=Decimal("200000"))],
            ),
        )

        with pytest.raises(AdjustmentError, match="only"):
            return_sale_items(database, sale.id, [{"product_id": product.id, "quantity": Decimal("500")}])

        return_sale_items(database, sale.id, [{"product_id": product.id, "quantity": Decimal("1")}])
        with pytest.raises(AdjustmentError, match="only"):
            return_sale_items(database, sale.id, [{"product_id": product.id, "quantity": Decimal("2")}])

        database.refresh(product)
        assert product.stock_quantity == Decimal("9.000"), "no phantom stock was invented"


def test_a_rejected_return_leaves_nothing_behind() -> None:
    with _session() as database:
        product = _product(database)
        sale = process_sale(
            database,
            SaleCreate(
                invoice_number="S-7",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("2"))],
                payment_lines=[SalePaymentLineInput(method="cash", amount=Decimal("200000"))],
            ),
        )
        with pytest.raises(AdjustmentError):
            return_sale_items(database, sale.id, [{"product_id": product.id, "quantity": Decimal("99")}])

        database.refresh(sale)
        database.refresh(product)
        assert sale.total == Decimal("200000.00")
        assert product.stock_quantity == Decimal("8.000")


# ── Purchase returns ─────────────────────────────────────────────────────

def test_purchase_return_reduces_what_is_owed_to_the_supplier() -> None:
    with _session() as database:
        product = _product(database, stock="0")
        supplier = Supplier(name="لبنیات پگاه", balance=Decimal("0"), is_active=True)
        database.add(supplier)
        database.commit()

        purchase = process_purchase(
            database,
            PurchaseCreate(
                invoice_number="P-1",
                supplier_id=supplier.id,
                items=[PurchaseItemCreate(product_id=product.id, quantity=Decimal("10"), unit_cost=Decimal("60000"))],
            ),
        )
        database.refresh(supplier)
        assert purchase.total == Decimal("600000.00")
        assert supplier.balance == Decimal("600000.00")

        return_purchase_items(database, purchase.id, [{"product_id": product.id, "quantity": Decimal("4")}])
        database.refresh(purchase)
        database.refresh(supplier)
        database.refresh(product)

        assert product.stock_quantity == Decimal("6.000")
        assert purchase.total == Decimal("360000.00")
        assert supplier.balance == Decimal("360000.00"), "no longer owed for milk that went back"


def test_purchase_return_takes_back_money_already_paid() -> None:
    with _session() as database:
        product = _product(database, stock="0")
        supplier = Supplier(name="لبنیات پگاه", balance=Decimal("0"), is_active=True)
        database.add(supplier)
        database.commit()

        purchase = process_purchase(
            database,
            PurchaseCreate(
                invoice_number="P-2",
                supplier_id=supplier.id,
                items=[PurchaseItemCreate(product_id=product.id, quantity=Decimal("10"), unit_cost=Decimal("60000"))],
                payment_lines=[{"method": "cash", "amount": Decimal("600000")}],
            ),
        )
        database.refresh(supplier)
        assert supplier.balance == Decimal("0.00")

        return_purchase_items(database, purchase.id, [{"product_id": product.id, "quantity": Decimal("5")}])
        database.refresh(purchase)
        database.refresh(supplier)

        assert purchase.total == Decimal("300000.00")
        assert purchase.paid_amount == Decimal("300000.00"), "the supplier hands half of it back"
        assert purchase.remaining_amount == Decimal("0.00")
        assert supplier.balance == Decimal("0.00")


def test_cannot_return_more_than_the_purchase_carried() -> None:
    with _session() as database:
        product = _product(database, stock="0")
        purchase = process_purchase(
            database,
            PurchaseCreate(
                invoice_number="P-3",
                items=[PurchaseItemCreate(product_id=product.id, quantity=Decimal("3"), unit_cost=Decimal("60000"))],
            ),
        )
        with pytest.raises(AdjustmentError, match="only"):
            return_purchase_items(database, purchase.id, [{"product_id": product.id, "quantity": Decimal("4")}])


# ── Shrinkage ────────────────────────────────────────────────────────────

def test_stock_can_be_written_off_and_never_below_zero() -> None:
    with _session() as database:
        product = _product(database, stock="10")

        adjust_stock(database, product.id, Decimal("-3"), reason="فاسد شده")
        database.refresh(product)
        assert product.stock_quantity == Decimal("7.000")

        with pytest.raises(AdjustmentError, match="Insufficient stock"):
            adjust_stock(database, product.id, Decimal("-99"))
        with pytest.raises(AdjustmentError, match="cannot be zero"):
            adjust_stock(database, product.id, Decimal("0"))


# ── Till reconciliation ──────────────────────────────────────────────────

def test_a_cash_refund_is_taken_out_of_the_expected_till() -> None:
    with _session() as database:
        product = _product(database)
        cashier = User(username="c", password_hash="x", full_name="صندوق‌دار", role="cashier")
        database.add(cashier)
        database.commit()

        shift = open_shift(database, cashier_id=cashier.id, opening_cash=Decimal("500000"))
        sale = process_sale(
            database,
            SaleCreate(
                invoice_number="S-8",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("2"))],
                payment_lines=[SalePaymentLineInput(method="cash", amount=Decimal("200000"))],
            ),
        )
        return_sale_items(database, sale.id, [{"product_id": product.id, "quantity": Decimal("1")}])

        # 500,000 float + 200,000 taken − 100,000 handed back.
        closed = close_shift(database, shift, closing_cash=Decimal("600000"))
        assert closed.expected_cash == Decimal("600000.00")
        assert closed.difference == Decimal("0.00"), "a refund is not a shortage"


def test_a_card_refund_never_touches_the_till() -> None:
    with _session() as database:
        product = _product(database)
        cashier = User(username="c", password_hash="x", full_name="صندوق‌دار", role="cashier")
        database.add(cashier)
        database.commit()

        shift = open_shift(database, cashier_id=cashier.id, opening_cash=Decimal("500000"))
        sale = process_sale(
            database,
            SaleCreate(
                invoice_number="S-9",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("2"))],
                payment_lines=[SalePaymentLineInput(method="card", amount=Decimal("200000"))],
            ),
        )
        return_sale_items(
            database, sale.id, [{"product_id": product.id, "quantity": Decimal("1")}],
            refund_method=PaymentMethod.CARD,
        )

        closed = close_shift(database, shift, closing_cash=Decimal("500000"))
        assert closed.expected_cash == Decimal("500000.00")
        assert closed.difference == Decimal("0.00")
