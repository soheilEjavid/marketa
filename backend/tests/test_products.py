from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.schemas.product import ProductCreate, ProductUpdate
from app.services.products import create_product, list_products, update_product


def test_product_lifecycle() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        # ProductCreate can still set an initial stock_quantity.
        product = create_product(
            database,
            ProductCreate(
                barcode="1001",
                name="Tea",
                purchase_price=Decimal("3.00"),
                sale_price=Decimal("4.50"),
                stock_quantity=Decimal("12"),
            ),
        )
        # ProductUpdate has no stock_quantity field at all — updating other
        # fields must leave stock untouched (stock only changes via
        # purchase/sale/adjustment from here on).
        update_product(
            database,
            product,
            ProductUpdate(name="Tea (updated)"),
        )
        products = list_products(database, search="Tea")

    assert len(products) == 1
    assert products[0].stock_quantity == Decimal("12.000")
    assert products[0].name == "Tea (updated)"
    assert not hasattr(ProductUpdate(), "stock_quantity")
