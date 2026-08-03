from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.entities import (
    Category,
    DocumentStatus,
    PaymentMethod,
    Product,
    Purchase,
    PurchaseItem,
    Sale,
    SaleItem,
)
from app.services.reports import diagnose_status, inflation_rate

PERIOD1_START = date(2026, 1, 1)
PERIOD1_END = date(2026, 1, 31)
PERIOD1_AT = datetime(2026, 1, 15, tzinfo=UTC)
PERIOD2_START = date(2026, 2, 1)
PERIOD2_END = date(2026, 2, 28)
PERIOD2_AT = datetime(2026, 2, 15, tzinfo=UTC)


def _make_product(database: Session, name: str, category: Category | None = None) -> Product:
    product = Product(
        name=name,
        purchase_price=Decimal("1"),
        sale_price=Decimal("1"),
        stock_quantity=Decimal("1000"),
        low_stock_threshold=Decimal("0"),
        is_active=True,
        category=category,
    )
    database.add(product)
    database.commit()
    database.refresh(product)
    return product


def _make_sale(database: Session, product: Product, *, quantity: str, unit_price: str, when: datetime) -> None:
    qty = Decimal(quantity)
    price = Decimal(unit_price)
    revenue = qty * price
    sale = Sale(
        invoice_number=f"INFL-S-{uuid4().hex[:10]}",
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
            product_id=product.id,
            quantity=qty,
            unit_price=price,
            cost_price=Decimal("1"),
            discount=Decimal("0"),
            line_total=revenue,
        )
    )
    database.commit()


def _make_purchase(database: Session, product: Product, *, quantity: str, unit_cost: str, when: datetime) -> None:
    qty = Decimal(quantity)
    cost = Decimal(unit_cost)
    total = qty * cost
    purchase = Purchase(
        invoice_number=f"INFL-P-{uuid4().hex[:10]}",
        status=DocumentStatus.COMPLETED,
        total=total,
        created_at=when,
    )
    database.add(purchase)
    database.flush()
    database.add(
        PurchaseItem(
            purchase_id=purchase.id,
            product_id=product.id,
            quantity=qty,
            unit_cost=cost,
            line_total=total,
            is_consignment=False,
        )
    )
    database.commit()


def test_inflation_rate_matches_hand_calculation() -> None:
    """
    HAND CALCULATION (checkable against the assertions below):

    5 products, each with a sale AND a purchase in both periods (>= the
    5-common-product minimum, so every index is computable).

    -- Sale side --
    Period 1 (qty, price -> revenue):
      P1: 10, 100 -> 1000   P2: 20, 50 -> 1000   P3: 10, 100 -> 1000
      P4: 10, 100 -> 1000   P5: 10, 100 -> 1000        sum revenue = 5000
    Period 2 (qty, price -> revenue):
      P1:  5, 130 -> 650    P2: 20, 60 -> 1200   P3: 20, 125 -> 2500
      P4: 10, 100 -> 1000   P5: 15, 150 -> 2250        sum revenue = 7600

    price_index = sum(price2 * qty1) / sum(price1 * qty1) * 100
      sum(price2*qty1) = 130*10 + 60*20 + 125*10 + 100*10 + 150*10
                        = 1300 + 1200 + 1250 + 1000 + 1500 = 6250
      = 6250 / 5000 * 100 = 125.0  ->  price_inflation_pct = 25.0

    volume_index = sum(price1 * qty2) / sum(price1 * qty1) * 100
      sum(price1*qty2) = 100*5 + 50*20 + 100*20 + 100*10 + 100*15
                        = 500 + 1000 + 2000 + 1000 + 1500 = 6000
      = 6000 / 5000 * 100 = 120.0  ->  volume_index_pct = 20.0

    -- Purchase side -- (all 5 products: qty 10 both periods, cost 60 -> 66)
      period1 total cost = 10*60*5   = 3000
      period2 total cost = 10*66*5   = 3300
      cost_index = sum(cost2*qty1)/sum(cost1*qty1)*100 = 3300/3000*100 = 110.0
      -> cost_inflation_pct = 10.0

    real_profit_index_pct = price_inflation_pct - cost_inflation_pct
                           = 25.0 - 10.0 = 15.0

    -- Revenue impact -- (Sale.total == the revenue figures above, so this
    is exactly what daily_sales_summary() would report for the same dates)
      nominal_p1 = 5000, nominal_p2 = 7600
      nominal_growth_pct = (7600-5000)/5000*100 = 52.0
      real_revenue_p2 = nominal_p2 / (price_index/100) = 7600 / 1.25 = 6080.0
      real_growth_pct = (6080-5000)/5000*100 = 21.6

    -- Diagnosis -- price up (+25%) and volume up (+20%) -> healthy_growth

    -- Top tables --
    price pct_change: P1=+30, P2=+20, P3=+25, P4=0, P5=+50
      -> sorted desc: P5, P1, P3, P2, P4
    volume pct_change: P1=-50, P2=0, P3=+100, P4=0, P5=+50
      -> sorted asc (biggest decline first): P1 first, at -50.0
    """
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        products = {name: _make_product(database, name) for name in ["P1", "P2", "P3", "P4", "P5"]}

        sale_data = {
            "P1": (("10", "100"), ("5", "130")),
            "P2": (("20", "50"), ("20", "60")),
            "P3": (("10", "100"), ("20", "125")),
            "P4": (("10", "100"), ("10", "100")),
            "P5": (("10", "100"), ("15", "150")),
        }
        for name, (p1, p2) in sale_data.items():
            _make_sale(database, products[name], quantity=p1[0], unit_price=p1[1], when=PERIOD1_AT)
            _make_sale(database, products[name], quantity=p2[0], unit_price=p2[1], when=PERIOD2_AT)

        for name in products:
            _make_purchase(database, products[name], quantity="10", unit_cost="60", when=PERIOD1_AT)
            _make_purchase(database, products[name], quantity="10", unit_cost="66", when=PERIOD2_AT)

        report = inflation_rate(
            database,
            period1_start=PERIOD1_START,
            period1_end=PERIOD1_END,
            period2_start=PERIOD2_START,
            period2_end=PERIOD2_END,
        )

        assert report["insufficient_data"] is False
        assert report["cost_inflation_pct"] == Decimal("10.0")
        assert report["price_inflation_pct"] == Decimal("25.0")
        assert report["volume_index_pct"] == Decimal("20.0")
        assert report["real_profit_index_pct"] == Decimal("15.0")

        impact = report["revenue_impact"]
        assert impact["nominal_revenue_p1"] == Decimal("5000")
        assert impact["nominal_revenue_p2"] == Decimal("7600")
        assert impact["nominal_growth_pct"] == Decimal("52.0")
        assert impact["real_revenue_p2"] == Decimal("6080.0")
        assert impact["real_growth_pct"] == Decimal("21.6")

        assert report["diagnosis"]["label"] == "healthy_growth"

        top_increases = report["top_price_increases"]
        assert [row["product_name"] for row in top_increases] == ["P5", "P1", "P3", "P2", "P4"]
        assert top_increases[0]["pct_change"] == Decimal("50")

        top_decliners = report["top_volume_decliners"]
        assert top_decliners[0]["product_name"] == "P1"
        assert top_decliners[0]["pct_change"] == Decimal("-50")


def test_diagnose_status_four_quadrants() -> None:
    """Direct unit test of the pure quadrant matrix from the doc's "تشخیص
    وضعیت اقتصادی فروشگاه" table — no DB/query involved."""
    healthy = diagnose_status(Decimal("10"), Decimal("5"))
    assert healthy["label"] == "healthy_growth"

    stagflation = diagnose_status(Decimal("10"), Decimal("-5"))
    assert stagflation["label"] == "stagflation"

    successful_competition = diagnose_status(Decimal("-10"), Decimal("5"))
    assert successful_competition["label"] == "successful_price_competition"

    real_recession = diagnose_status(Decimal("-10"), Decimal("-5"))
    assert real_recession["label"] == "real_price_recession"

    assert diagnose_status(None, Decimal("5")) is None
    assert diagnose_status(Decimal("5"), None) is None


def test_insufficient_data_store_wide_below_five_common_products() -> None:
    """Only 3 products with a sale in both periods -> below
    MIN_COMMON_PRODUCTS(5); the whole report must say so, not show a number
    computed from too little data."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        for name in ["A", "B", "C"]:
            product = _make_product(database, name)
            _make_sale(database, product, quantity="1", unit_price="10", when=PERIOD1_AT)
            _make_sale(database, product, quantity="1", unit_price="10", when=PERIOD2_AT)

        report = inflation_rate(
            database,
            period1_start=PERIOD1_START,
            period1_end=PERIOD1_END,
            period2_start=PERIOD2_START,
            period2_end=PERIOD2_END,
        )

        assert report["insufficient_data"] is True
        assert report["price_inflation_pct"] is None
        assert report["volume_index_pct"] is None
        assert report["diagnosis"] is None


def test_insufficient_data_per_category_even_when_store_wide_is_fine() -> None:
    """Store-wide has 6 common products (sufficient), but one category only
    has 2 of them — that category must independently report insufficient
    data even though the store-wide total does not."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        category_a = Category(name="دسته الف")
        category_b = Category(name="دسته ب")
        database.add_all([category_a, category_b])
        database.commit()

        for name in ["A1", "A2", "A3", "A4"]:
            product = _make_product(database, name, category=category_a)
            _make_sale(database, product, quantity="1", unit_price="10", when=PERIOD1_AT)
            _make_sale(database, product, quantity="1", unit_price="10", when=PERIOD2_AT)

        for name in ["B1", "B2"]:
            product = _make_product(database, name, category=category_b)
            _make_sale(database, product, quantity="1", unit_price="10", when=PERIOD1_AT)
            _make_sale(database, product, quantity="1", unit_price="10", when=PERIOD2_AT)

        report = inflation_rate(
            database,
            period1_start=PERIOD1_START,
            period1_end=PERIOD1_END,
            period2_start=PERIOD2_START,
            period2_end=PERIOD2_END,
        )

        # Store-wide: 4 + 2 = 6 common products -> sufficient.
        assert report["insufficient_data"] is False

        by_category = {row["category_name"]: row for row in report["by_category"]}
        assert by_category["دسته الف"]["insufficient_data"] is True
        assert by_category["دسته ب"]["insufficient_data"] is True


def test_price_decrease_is_labeled_as_decline_not_raw_negative() -> None:
    """A genuine price-decrease scenario: price_inflation_pct must come back
    negative (it's a real number, not an error), and the diagnosis text must
    frame it as a decline in words, never a bare "-X%" with no context."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        for name in ["D1", "D2", "D3", "D4", "D5"]:
            product = _make_product(database, name)
            # Price drops 10% every product; quantity sold goes UP (a
            # deliberate price-cut scenario) so this lands in the
            # "successful_price_competition" quadrant, not recession.
            _make_sale(database, product, quantity="10", unit_price="100", when=PERIOD1_AT)
            _make_sale(database, product, quantity="15", unit_price="90", when=PERIOD2_AT)

        report = inflation_rate(
            database,
            period1_start=PERIOD1_START,
            period1_end=PERIOD1_END,
            period2_start=PERIOD2_START,
            period2_end=PERIOD2_END,
        )

        assert report["price_inflation_pct"] == Decimal("-10.0")
        assert report["price_inflation_pct"] < 0

        diagnosis = report["diagnosis"]
        assert diagnosis["label"] == "successful_price_competition"
        assert "کاهش قیمت" in diagnosis["summary_sentence"]
        # No raw signed number ever appears in the generated sentence.
        assert "-" not in diagnosis["summary_sentence"]
