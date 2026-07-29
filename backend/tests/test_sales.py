from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.entities import Customer, Product, SalePaymentLine
from app.schemas.sale import SaleCreate, SaleItemCreate, SalePaymentLineInput
from app.services.sales import SaleError, process_sale, get_sale, list_sales


def test_get_sale_returns_sale_with_items() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        product = Product(
            name="Tea",
            purchase_price=Decimal("5"),
            sale_price=Decimal("10"),
            stock_quantity=Decimal("100"),
            low_stock_threshold=Decimal("2"),
            is_active=True,
        )
        database.add(product)
        database.commit()
        database.refresh(product)

        created = process_sale(
            database,
            SaleCreate(
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("3"))]
            ),
        )

        fetched = get_sale(database, created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.invoice_number == created.invoice_number
        assert fetched.total == Decimal("30.00")
        assert len(fetched.items) == 1
        assert fetched.items[0].product_id == product.id
        assert fetched.items[0].quantity == Decimal("3.000")


def test_get_sale_returns_none_for_missing() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        result = get_sale(database, 999)
        assert result is None


def test_list_sales_returns_ordered() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        product = Product(
            name="Tea",
            purchase_price=Decimal("5"),
            sale_price=Decimal("10"),
            stock_quantity=Decimal("100"),
            low_stock_threshold=Decimal("2"),
            is_active=True,
        )
        database.add(product)
        database.commit()
        database.refresh(product)

        process_sale(database, SaleCreate(items=[SaleItemCreate(product_id=product.id, quantity=Decimal("1"))]))
        process_sale(database, SaleCreate(items=[SaleItemCreate(product_id=product.id, quantity=Decimal("2"))]))

        sales = list_sales(database)
        assert len(sales) >= 2


def _make_product(database: Session, *, stock: str = "100") -> Product:
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


# ── Split/combined payment for sales (parity with purchases) ────────────


def test_legacy_single_payment_method_still_works_unchanged() -> None:
    """No payment_lines sent — the pre-existing single payment_method +
    paid_amount behavior must be byte-identical, and it must now also
    synthesize exactly one SalePaymentLine for shift reconciliation.
    """
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        product = _make_product(database)

        sale = process_sale(
            database,
            SaleCreate(
                payment_method="cash",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("2"))],
            ),
        )

        assert sale.payment_method == "cash"
        assert sale.paid_amount == Decimal("20.00")
        assert sale.remaining_amount == Decimal("0.00")
        assert sale.payment_status == "paid"

        lines = database.query(SalePaymentLine).filter_by(sale_id=sale.id).all()
        assert len(lines) == 1
        assert lines[0].method == "cash"
        assert lines[0].amount == Decimal("20.00")


def test_legacy_credit_sale_creates_no_payment_line() -> None:
    """A credit sale with nothing paid now should not fabricate a cash/card
    line — there was no real tender to reconcile."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        product = _make_product(database)
        customer = Customer(full_name="Credit Customer", credit_limit=Decimal("100000"))
        database.add(customer)
        database.commit()
        database.refresh(customer)

        sale = process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                payment_method="credit",
                paid_amount=Decimal("0"),
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("2"))],
            ),
        )

        assert sale.paid_amount == Decimal("0.00")
        lines = database.query(SalePaymentLine).filter_by(sale_id=sale.id).all()
        assert lines == []


def test_multi_line_cash_and_card_payment() -> None:
    """A walk-in sale split cash+card: both lines persisted, totals correct,
    payment_method displayed as 'mixed'."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        product = _make_product(database)

        sale = process_sale(
            database,
            SaleCreate(
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("10"))],  # total = 100
                payment_lines=[
                    SalePaymentLineInput(method="cash", amount=Decimal("60")),
                    SalePaymentLineInput(method="card", amount=Decimal("40")),
                ],
            ),
        )

        assert sale.total == Decimal("100.00")
        assert sale.paid_amount == Decimal("100.00")
        assert sale.remaining_amount == Decimal("0.00")
        assert sale.payment_method == "mixed"

        lines = database.query(SalePaymentLine).filter_by(sale_id=sale.id).order_by(SalePaymentLine.id).all()
        assert [(line.method, line.amount) for line in lines] == [
            ("cash", Decimal("60.00")),
            ("card", Decimal("40.00")),
        ]


def test_multi_line_payment_exceeding_remainder_raises() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        product = _make_product(database)

        with pytest.raises(SaleError):
            process_sale(
                database,
                SaleCreate(
                    items=[SaleItemCreate(product_id=product.id, quantity=Decimal("10"))],  # total = 100
                    payment_lines=[
                        SalePaymentLineInput(method="cash", amount=Decimal("60")),
                        SalePaymentLineInput(method="card", amount=Decimal("60")),
                    ],
                ),
            )


def test_multi_line_payment_validated_against_post_redemption_remainder() -> None:
    """Payment lines are checked against what's left AFTER points redemption,
    not the full invoice total."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        product = _make_product(database, stock="2000")
        customer = Customer(full_name="Loyal Customer", credit_limit=Decimal("100000"), loyalty_points_balance=100, loyalty_member=True)
        database.add(customer)
        database.commit()
        database.refresh(customer)

        # total = 1000 * 10 = 10,000. redeem_points=6 -> 6*500=3,000 toman,
        # exactly the 30% cap (not exceeding it) -> remaining = 7,000.
        sale = process_sale(
            database,
            SaleCreate(
                customer_id=customer.id,
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("1000"))],
                redeem_points=6,
                payment_lines=[SalePaymentLineInput(method="cash", amount=Decimal("7000"))],
            ),
        )
        assert sale.total == Decimal("10000.00")
        assert sale.remaining_amount == Decimal("0.00")
        assert sale.paid_amount == Decimal("10000.00")

        # Lines summing to MORE than the post-redemption remainder (7,000)
        # must still be rejected, even though they're well under the total.
        with pytest.raises(SaleError):
            process_sale(
                database,
                SaleCreate(
                    customer_id=customer.id,
                    items=[SaleItemCreate(product_id=product.id, quantity=Decimal("1000"))],
                    redeem_points=6,
                    payment_lines=[SalePaymentLineInput(method="cash", amount=Decimal("7001"))],
                ),
            )