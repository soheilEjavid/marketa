"""What the goods on the shelf actually cost.

Restocking used to replace `Product.purchase_price` with the newest
delivery's price, which says every unit on the shelf was bought at that
price — only true when the shelf was empty. With stock left from a cheaper
batch it overstates cost, understates margin, and inflates the inventory
valuation.

Dual pricing made it worst, because there the shop *knows* two batches are
mixed and was still costing the whole lot at the newer price. But the error
was never confined to dual-priced products: it applied to any restock at a
new price with stock still on hand.
"""

from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.entities import Product, SaleItem
from app.schemas.purchase import PurchaseCreate, PurchaseItemCreate
from app.schemas.sale import SaleCreate, SaleItemCreate, SalePaymentLineInput
from app.services.products import collapse_dual_pricing, weighted_average_cost
from app.services.purchases import process_purchase
from app.services.sales import process_sale


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def _product(database: Session, *, stock="0", cost="0", price="100000") -> Product:
    product = Product(
        name="برنج", purchase_price=Decimal(cost), sale_price=Decimal(price),
        stock_quantity=Decimal(stock), low_stock_threshold=Decimal("0"), is_active=True,
    )
    database.add(product)
    database.commit()
    database.refresh(product)
    return product


def test_the_two_batch_case_by_hand() -> None:
    """10 at 50,000 then 20 at 65,000 is 30 units that cost 60,000 each:
    (10×50,000 + 20×65,000) / 30 = 1,800,000 / 30 = 60,000."""
    with _session() as database:
        product = _product(database)

        process_purchase(database, PurchaseCreate(
            invoice_number="P-1",
            items=[PurchaseItemCreate(product_id=product.id, quantity=Decimal("10"),
                                      unit_cost=Decimal("50000"))]))
        database.refresh(product)
        assert product.purchase_price == Decimal("50000.00"), "empty shelf: the delivery sets the cost"

        process_purchase(database, PurchaseCreate(
            invoice_number="P-2", confirm_dual_pricing=True,
            items=[PurchaseItemCreate(product_id=product.id, quantity=Decimal("20"),
                                      unit_cost=Decimal("65000"))]))
        database.refresh(product)

        assert product.stock_quantity == Decimal("30.000")
        assert product.purchase_price == Decimal("60000.00")
        # And the shelf is worth what was actually paid for it, to the rial.
        assert product.stock_quantity * product.purchase_price == Decimal("1800000.000")


def test_the_helper_alone() -> None:
    assert weighted_average_cost(Decimal("10"), Decimal("50000"),
                                 Decimal("20"), Decimal("65000")) == Decimal("60000.00")
    # An empty shelf has nothing to average against.
    assert weighted_average_cost(Decimal("0"), Decimal("999"),
                                 Decimal("5"), Decimal("400")) == Decimal("400.00")
    # Negative stock would produce a nonsense weight; the delivery wins.
    assert weighted_average_cost(Decimal("-3"), Decimal("999"),
                                 Decimal("5"), Decimal("400")) == Decimal("400.00")
    # Nothing delivered, nothing to blend.
    assert weighted_average_cost(Decimal("10"), Decimal("500"),
                                 Decimal("0"), Decimal("400")) == Decimal("500.00")
    # Thirds round to the two decimals every money column carries.
    assert weighted_average_cost(Decimal("1"), Decimal("100"),
                                 Decimal("2"), Decimal("101")) == Decimal("100.67")


def test_a_dual_priced_sale_costs_the_same_on_either_tier() -> None:
    """The tier decides what the customer pays, never what the goods cost:
    the two batches are mixed in the stockroom and nobody can say which
    carton this was. Costing the old tier at the older price used to
    flatter the margin on exactly the sales earning least."""
    with _session() as database:
        product = _product(database)
        process_purchase(database, PurchaseCreate(
            invoice_number="P-1",
            items=[PurchaseItemCreate(product_id=product.id, quantity=Decimal("10"),
                                      unit_cost=Decimal("50000"), selling_price=Decimal("80000"))]))
        process_purchase(database, PurchaseCreate(
            invoice_number="P-2", confirm_dual_pricing=True,
            dual_pricing_new_sale_prices={product.id: 100000},
            items=[PurchaseItemCreate(product_id=product.id, quantity=Decimal("20"),
                                      unit_cost=Decimal("65000"))]))
        database.refresh(product)
        assert product.is_dual_priced is True
        assert product.purchase_price == Decimal("60000.00")

        for tier, expected_price in (("old", Decimal("80000.00")), ("new", Decimal("100000.00"))):
            sale = process_sale(database, SaleCreate(
                invoice_number=f"S-{tier}",
                items=[SaleItemCreate(product_id=product.id, quantity=Decimal("1"), price_tier=tier)],
                payment_lines=[SalePaymentLineInput(method="cash", amount=expected_price)]))
            line = database.scalars(select(SaleItem).where(SaleItem.sale_id == sale.id)).one()
            assert line.unit_price == expected_price, "the customer pays the tier's price"
            assert line.cost_price == Decimal("60000.00"), "but the goods cost one blended figure"


def test_collapsing_the_price_split_leaves_the_cost_alone() -> None:
    """Going back to a single sale price is a marketing decision. It used to
    drag purchase_price back to the earlier batch's price, throwing away the
    blend and rewriting what the stock had cost."""
    with _session() as database:
        product = _product(database)
        process_purchase(database, PurchaseCreate(
            invoice_number="P-1",
            items=[PurchaseItemCreate(product_id=product.id, quantity=Decimal("10"),
                                      unit_cost=Decimal("50000"), selling_price=Decimal("80000"))]))
        process_purchase(database, PurchaseCreate(
            invoice_number="P-2", confirm_dual_pricing=True,
            dual_pricing_new_sale_prices={product.id: 100000},
            items=[PurchaseItemCreate(product_id=product.id, quantity=Decimal("20"),
                                      unit_cost=Decimal("65000"))]))
        database.refresh(product)

        collapse_dual_pricing(database, product, keep_tier="old")
        database.refresh(product)
        assert product.is_dual_priced is False
        assert product.sale_price == Decimal("80000.00"), "the old tier's sale price is kept"
        assert product.purchase_price == Decimal("60000.00"), "the blended cost survives"


def test_an_ordinary_restock_blends_too() -> None:
    """No dual pricing involved — the same error, and the same fix."""
    with _session() as database:
        product = _product(database, stock="4", cost="5")
        process_purchase(database, PurchaseCreate(
            invoice_number="P-1", confirm_dual_pricing=True,
            items=[PurchaseItemCreate(product_id=product.id, quantity=Decimal("6"),
                                      unit_cost=Decimal("6.25"))]))
        database.refresh(product)
        # (4×5 + 6×6.25) / 10 = 5.75, not the 6.25 a replacement would claim.
        assert product.purchase_price == Decimal("5.75")
