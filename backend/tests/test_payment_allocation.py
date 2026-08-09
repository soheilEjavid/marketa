"""A payment against a party's balance has to settle their open invoices.

Without it, `customer.balance` and the sum of that customer's unpaid
invoices drifted apart by exactly the amount ever paid this way — the
balance said settled, the invoice list said nothing had been paid at all.
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
    PaymentStatus,
    Product,
    Sale,
    Supplier,
)
from app.schemas.financial import PaymentCreate
from app.schemas.purchase import PurchaseCreate, PurchaseItemCreate
from app.schemas.sale import SaleCreate, SaleItemCreate
from app.services.financials import FinancialError, record_customer_payment, record_supplier_payment
from app.services.purchases import process_purchase
from app.services.sales import process_sale


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def _product(database: Session) -> Product:
    product = Product(
        name="برنج",
        purchase_price=Decimal("60000"),
        sale_price=Decimal("100000"),
        stock_quantity=Decimal("1000"),
        low_stock_threshold=Decimal("2"),
        is_active=True,
    )
    database.add(product)
    database.commit()
    database.refresh(product)
    return product


def _credit_sale(database: Session, customer: Customer, product: Product, units: str, invoice: str) -> Sale:
    return process_sale(
        database,
        SaleCreate(
            invoice_number=invoice,
            customer_id=customer.id,
            payment_method="credit",
            paid_amount=Decimal("0"),
            items=[SaleItemCreate(product_id=product.id, quantity=Decimal(units))],
        ),
    )


def _customer(database: Session) -> Customer:
    customer = Customer(full_name="مشتری", balance=Decimal("0"), credit_limit=Decimal("0"))
    database.add(customer)
    database.commit()
    database.refresh(customer)
    return customer


def test_a_balance_payment_settles_the_oldest_invoices_first() -> None:
    with _session() as database:
        product = _product(database)
        customer = _customer(database)
        first = _credit_sale(database, customer, product, "1", "S-1")    # 100,000
        second = _credit_sale(database, customer, product, "2", "S-2")   # 200,000
        third = _credit_sale(database, customer, product, "1", "S-3")    # 100,000
        database.refresh(customer)
        assert customer.balance == Decimal("400000.00")

        record_customer_payment(database, customer, PaymentCreate(amount=Decimal("250000"), method="cash"))

        for sale in (first, second, third):
            database.refresh(sale)
        assert first.payment_status == PaymentStatus.PAID
        assert first.remaining_amount == Decimal("0.00")
        assert second.payment_status == PaymentStatus.PARTIAL
        assert second.remaining_amount == Decimal("50000.00")
        assert third.payment_status == PaymentStatus.UNPAID, "the newest debt is settled last"
        assert third.remaining_amount == Decimal("100000.00")


def test_balance_and_open_invoices_agree_after_settling_up() -> None:
    with _session() as database:
        product = _product(database)
        customer = _customer(database)
        _credit_sale(database, customer, product, "1", "S-1")
        _credit_sale(database, customer, product, "2", "S-2")
        database.refresh(customer)

        record_customer_payment(database, customer, PaymentCreate(amount=Decimal("300000"), method="cash"))
        database.refresh(customer)

        open_total = sum(
            (sale.remaining_amount for sale in database.scalars(
                select(Sale).where(Sale.customer_id == customer.id, Sale.status == DocumentStatus.COMPLETED)
            )),
            Decimal("0"),
        )
        assert customer.balance == Decimal("0.00")
        assert open_total == customer.balance, "the two numbers a shopkeeper compares must match"


def test_the_payment_row_stays_unallocated_so_the_till_still_sees_the_cash() -> None:
    with _session() as database:
        product = _product(database)
        customer = _customer(database)
        _credit_sale(database, customer, product, "1", "S-1")
        database.refresh(customer)

        record_customer_payment(database, customer, PaymentCreate(amount=Decimal("100000"), method="cash"))

        payments = database.scalars(
            select(CustomerPayment).where(CustomerPayment.customer_id == customer.id)
        ).all()
        assert len(payments) == 1
        assert payments[0].sale_id is None, (
            "close_shift() keys the walk-in cash it counts on sale_id being null"
        )


def test_settling_more_than_is_owed_is_still_refused() -> None:
    with _session() as database:
        product = _product(database)
        customer = _customer(database)
        _credit_sale(database, customer, product, "1", "S-1")
        database.refresh(customer)

        with pytest.raises(FinancialError, match="outstanding balance"):
            record_customer_payment(database, customer, PaymentCreate(amount=Decimal("999999"), method="cash"))


def test_paying_a_named_invoice_still_only_touches_that_invoice() -> None:
    with _session() as database:
        product = _product(database)
        customer = _customer(database)
        first = _credit_sale(database, customer, product, "1", "S-1")
        second = _credit_sale(database, customer, product, "1", "S-2")

        record_customer_payment(
            database, customer,
            PaymentCreate(amount=Decimal("100000"), method="cash", document_id=second.id),
        )
        database.refresh(first)
        database.refresh(second)

        assert second.payment_status == PaymentStatus.PAID
        assert first.payment_status == PaymentStatus.UNPAID, "an explicit choice is not overridden"


def test_supplier_balance_payments_settle_their_oldest_purchases() -> None:
    with _session() as database:
        product = _product(database)
        supplier = Supplier(name="تأمین‌کننده", balance=Decimal("0"), is_active=True)
        database.add(supplier)
        database.commit()

        first = process_purchase(
            database,
            PurchaseCreate(
                invoice_number="P-1", supplier_id=supplier.id,
                items=[PurchaseItemCreate(product_id=product.id, quantity=Decimal("1"), unit_cost=Decimal("60000"))],
            ),
        )
        second = process_purchase(
            database,
            PurchaseCreate(
                invoice_number="P-2", supplier_id=supplier.id,
                confirm_dual_pricing=True,
                items=[PurchaseItemCreate(product_id=product.id, quantity=Decimal("2"), unit_cost=Decimal("60000"))],
            ),
        )
        database.refresh(supplier)
        assert supplier.balance == Decimal("180000.00")

        record_supplier_payment(database, supplier, PaymentCreate(amount=Decimal("100000"), method="cash"))
        database.refresh(first)
        database.refresh(second)
        database.refresh(supplier)

        assert first.payment_status == PaymentStatus.PAID
        assert second.remaining_amount == Decimal("80000.00")
        assert supplier.balance == Decimal("80000.00")
