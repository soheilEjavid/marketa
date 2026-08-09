"""The demo seeder must not write stock without a movement behind it.

Its dead-stock top-up used to assign Product.stock_quantity directly, so a
seeded database shipped with a product whose shelf figure ran ahead of the
sum of its own inventory transactions — the ledger every other stock number
in this app is checked against. Whether that branch is taken at all depends
on the run's random draw, so this exercises it deliberately rather than
hoping a full seed happens to hit it.
"""

import random
from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.entities import (
    InventoryTransaction,
    InventoryTransactionType,
    Product,
)
from app.seed import _finishing_touches


def _product(database: Session, name: str, stock: str, popularity: float) -> Product:
    product = Product(
        name=name,
        purchase_price=Decimal("60000"),
        sale_price=Decimal("100000"),
        stock_quantity=Decimal(stock),
        low_stock_threshold=Decimal("2"),
        is_active=True,
    )
    database.add(product)
    database.commit()
    database.refresh(product)
    # The seeder hangs these on the ORM objects as it builds them.
    product._popularity = popularity
    product._shelf_life = None
    return product


def test_dead_stock_top_up_posts_a_real_inventory_movement() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as database:
        # Every one of these is under the seeder's threshold of 12, so the
        # top-up branch is guaranteed to run for all of them.
        products = [
            _product(database, "دارچین ۸۰ گرم", "7", 0.01),
            _product(database, "زعفران ۱ گرم", "3", 0.02),
            _product(database, "هل سبز", "0", 0.03),
        ]
        # Each carries an opening movement, so a balanced ledger afterwards
        # can only mean the top-up posted one of its own.
        for product in products:
            database.add(
                InventoryTransaction(
                    product_id=product.id,
                    quantity_change=product.stock_quantity,
                    transaction_type=InventoryTransactionType.PURCHASE,
                    related_id=None,
                )
            )
        database.commit()

        _finishing_touches(
            database,
            random.Random(7),
            {"products": products, "counters": {"dual_priced": 0}},
        )
        database.commit()

        for product in products:
            database.refresh(product)
            ledgered = database.scalar(
                select(func.coalesce(func.sum(InventoryTransaction.quantity_change), 0)).where(
                    InventoryTransaction.product_id == product.id
                )
            )
            assert product.stock_quantity == Decimal(str(ledgered)), (
                f"{product.name}: shelf {product.stock_quantity} vs ledger {ledgered}"
            )
            assert product.stock_quantity >= 14, "the top-up should have raised the shelf"

        adjustments = database.scalars(
            select(InventoryTransaction).where(
                InventoryTransaction.transaction_type == InventoryTransactionType.ADJUSTMENT
            )
        ).all()
        assert len(adjustments) == len(products), "one movement per topped-up line"
        assert all(row.quantity_change > 0 for row in adjustments)
