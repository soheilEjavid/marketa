"""Cancelling an invoice has to undo it, not hide it.

There was no way to void a completed sale at all — a cashier who rang up
the wrong thing could edit the invoice but never take it back. "Delete" is
the wrong shape for a document that has been issued: the number is on a
receipt in somebody's bag and the audit log points at its id. So this
reverses the sale and marks it CANCELLED, which every report already
excludes — from the shopkeeper's side it is gone, and from the books' side
it is accounted for.
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.entities import (
    Customer,
    DocumentStatus,
    PaymentMethod,
    Product,
    Sale,
    SalePaymentLine,
)
from app.schemas.sale import SaleCreate, SaleItemCreate, SalePaymentLineInput
from app.services.adjustments import AdjustmentError, cancel_sale
from app.services.reports import daily_sales_summary, payment_method_breakdown
from app.services.sales import hold_sale, list_sales, process_sale


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def _product(database: Session) -> Product:
    product = Product(
        name="پنیر", purchase_price=Decimal("60000"), sale_price=Decimal("100000"),
        stock_quantity=Decimal("50"), low_stock_threshold=Decimal("0"), is_active=True,
    )
    database.add(product)
    database.commit()
    database.refresh(product)
    return product


def _paid_sale(database: Session, product: Product, invoice: str = "S-1") -> Sale:
    return process_sale(
        database,
        SaleCreate(
            invoice_number=invoice,
            items=[SaleItemCreate(product_id=product.id, quantity=Decimal("3"))],
            payment_lines=[SalePaymentLineInput(method="cash", amount=Decimal("300000"))],
        ),
    )


def test_cancelling_puts_the_goods_back_and_the_money_out() -> None:
    with _session() as database:
        product = _product(database)
        sale = _paid_sale(database, product)
        database.refresh(product)
        assert product.stock_quantity == Decimal("47.000")

        cancel_sale(database, sale, reason="اشتباه صندوق‌دار")
        database.refresh(sale)
        database.refresh(product)

        assert sale.status == DocumentStatus.CANCELLED
        assert sale.total == Decimal("0.00")
        assert product.stock_quantity == Decimal("50.000"), "the goods come back"

        refund = database.scalar(
            select(SalePaymentLine).where(
                SalePaymentLine.sale_id == sale.id, SalePaymentLine.amount < 0
            )
        )
        assert refund is not None and refund.amount == Decimal("-300000.00")
        assert refund.method == PaymentMethod.CASH


def test_a_cancelled_invoice_stops_counting_everywhere() -> None:
    with _session() as database:
        product = _product(database)
        kept = _paid_sale(database, product, "S-KEEP")
        voided = _paid_sale(database, product, "S-VOID")

        assert sum(row["total_sales"] for row in daily_sales_summary(database)) == Decimal("600000.00")

        cancel_sale(database, voided, reason="فاکتور تکراری")

        rows = daily_sales_summary(database)
        assert sum(row["total_sales"] for row in rows) == Decimal("300000.00"), "only the kept sale"
        assert sum(row["profit"] for row in rows) == Decimal("120000.00"), "3 × (100k − 60k)"

        tendered = sum(row["total"] for row in payment_method_breakdown(database))
        assert tendered == Decimal("300000.00"), "the voided tender is gone from the breakdown too"

        listed = [s.invoice_number for s in list_sales(database)]
        assert listed == [kept.invoice_number], "and it drops out of the history list"


def test_a_manager_can_still_see_what_was_voided() -> None:
    """Hidden by default, but never gone: "it vanished" is a worse answer
    than showing the invoice struck through, and a voided document is
    exactly the one somebody eventually asks about."""
    with _session() as database:
        product = _product(database)
        kept = _paid_sale(database, product, "S-KEEP")
        voided = _paid_sale(database, product, "S-VOID")
        cancel_sale(database, voided, reason="فاکتور تکراری")

        default_view = [s.invoice_number for s in list_sales(database)]
        assert default_view == [kept.invoice_number]

        manager_view = list_sales(database, include_cancelled=True)
        by_number = {s.invoice_number: s.status for s in manager_view}
        assert by_number == {
            kept.invoice_number: DocumentStatus.COMPLETED,
            voided.invoice_number: DocumentStatus.CANCELLED,
        }, "both are listed, and the voided one says so"


def test_the_invoice_and_its_number_survive_for_the_audit_trail() -> None:
    with _session() as database:
        product = _product(database)
        sale = _paid_sale(database, product, "S-KEEPNUMBER")
        cancel_sale(database, sale, reason="مرجوعی کامل")

        still_there = database.scalar(select(Sale).where(Sale.id == sale.id))
        assert still_there is not None, "the row is never deleted"
        assert still_there.invoice_number == "S-KEEPNUMBER", "nor is the number freed for reuse"


def test_a_credit_sale_cancellation_clears_what_the_customer_owed() -> None:
    with _session() as database:
        product = _product(database)
        customer = Customer(full_name="مشتری", balance=Decimal("0"), credit_limit=Decimal("0"))
        database.add(customer)
        database.commit()

        sale = process_sale(
            database,
            SaleCreate(
                invoice_number="S-CREDIT", customer_id=customer.id,
                payment_method="credit", paid_amount=Decimal("0"),
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("2"))],
            ),
        )
        database.refresh(customer)
        assert customer.balance == Decimal("200000.00")

        cancel_sale(database, sale, reason="کالا تحویل نشد")
        database.refresh(customer)
        assert customer.balance == Decimal("0.00"), "they owe nothing for a sale that was voided"


def test_the_refund_goes_back_the_way_the_money_came_in() -> None:
    """close_shift subtracts cash refunds from the expected till and ignores
    card ones, because card money never passed through the drawer. Refunding
    a card sale in cash would invent a shortage of the whole invoice at the
    end of the shift."""
    with _session() as database:
        product = _product(database)
        sale = process_sale(
            database,
            SaleCreate(
                invoice_number="S-CARD",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("2"))],
                payment_lines=[SalePaymentLineInput(method="card", amount=Decimal("200000"))],
            ),
        )
        cancel_sale(database, sale, reason="اشتباه")

        refund = database.scalar(
            select(SalePaymentLine).where(
                SalePaymentLine.sale_id == sale.id, SalePaymentLine.amount < 0
            )
        )
        assert refund.method == PaymentMethod.CARD, "not cash — the till never held this money"
        assert refund.amount == Decimal("-200000.00")


def test_a_split_payment_is_refunded_to_whichever_tender_paid_most() -> None:
    with _session() as database:
        product = _product(database)
        sale = process_sale(
            database,
            SaleCreate(
                invoice_number="S-SPLIT",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("3"))],
                payment_lines=[
                    SalePaymentLineInput(method="cash", amount=Decimal("100000")),
                    SalePaymentLineInput(method="card", amount=Decimal("200000")),
                ],
            ),
        )
        cancel_sale(database, sale, reason="اشتباه")

        refund = database.scalar(
            select(SalePaymentLine).where(
                SalePaymentLine.sale_id == sale.id, SalePaymentLine.amount < 0
            )
        )
        assert refund.method == PaymentMethod.CARD, "the larger share came in on the card"


def test_cancelling_twice_is_refused() -> None:
    with _session() as database:
        product = _product(database)
        sale = _paid_sale(database, product)
        cancel_sale(database, sale, reason="اشتباه")
        database.refresh(sale)

        with pytest.raises(AdjustmentError, match="already cancelled"):
            cancel_sale(database, sale, reason="دوباره")


def test_a_held_draft_is_not_cancelled_this_way() -> None:
    with _session() as database:
        product = _product(database)
        draft = hold_sale(
            database,
            SaleCreate(
                invoice_number="S-DRAFT",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("1"))],
            ),
        )
        with pytest.raises(AdjustmentError, match="Only a completed invoice"):
            cancel_sale(database, draft, reason="whatever")


def test_a_reason_is_required() -> None:
    with _session() as database:
        product = _product(database)
        sale = _paid_sale(database, product)
        with pytest.raises(AdjustmentError, match="reason is required"):
            cancel_sale(database, sale, reason="   ")

        database.refresh(sale)
        assert sale.status == DocumentStatus.COMPLETED, "a refused cancel changes nothing"
