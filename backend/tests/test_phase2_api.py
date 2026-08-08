import asyncio
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes.inventory import get_inventory_transactions
from app.api.routes.purchases import create_purchase
from app.api.routes.sales import create_sale
from app.models.base import Base
from app.models.entities import Product, User
from app.schemas.purchase import PurchaseCreate, PurchaseItemCreate
from app.schemas.sale import SaleCreate, SaleItemCreate


def test_phase2_routes_process_documents_and_list_inventory() -> None:
    engine = create_engine(
        "sqlite://",
    )
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)

    with TestingSession() as database:
        product = Product(
            name="Tea",
            purchase_price=Decimal("5"),
            sale_price=Decimal("10"),
            stock_quantity=Decimal("4"),
            low_stock_threshold=Decimal("2"),
            is_active=True,
        )
        # These routes are called directly, so FastAPI never resolves their
        # Depends(require_role(...)) parameter — current_user has to be passed
        # by hand or it arrives as the Depends object itself and record_audit()
        # blows up on current_user.id.
        operator = User(
            username="phase2-admin",
            password_hash="x",
            full_name="Phase 2 Admin",
            role="admin",
        )
        database.add_all([product, operator])
        database.commit()
        database.refresh(product)
        database.refresh(operator)
        product_id = product.id
        operator_id = operator.id

    with TestingSession() as database:
        purchase = asyncio.run(
            create_purchase(
                PurchaseCreate(
                    # Restocking at a new cost with stock still on hand trips
                    # the dual-pricing confirmation gate; confirming without
                    # dual_pricing_new_sale_prices keeps this a plain
                    # single-price purchase (see services/purchases.py).
                    confirm_dual_pricing=True,
                    items=[
                        PurchaseItemCreate(
                            product_id=product_id,
                            quantity=Decimal("6"),
                            unit_cost=Decimal("6.25"),
                        )
                    ]
                ),
                database,
                database.get(User, operator_id),
            )
        )
        sale = asyncio.run(
            create_sale(
                SaleCreate(
                    payment_method="cash",
                    items=[
                        SaleItemCreate(
                            product_id=product_id,
                            quantity=Decimal("3"),
                        )
                    ],
                ),
                database,
                database.get(User, operator_id),
            )
        )
        transactions = asyncio.run(
            get_inventory_transactions(
                database=database,
                product_id=None,
                transaction_type=None,
                offset=0,
                limit=100,
            ),
        )

    assert purchase.total == Decimal("37.50")
    assert sale.total == Decimal("30.00")
    assert [
        transaction["quantity_change"] for transaction in reversed(transactions)
    ] == [Decimal("6.000"), Decimal("-3.000")]

    with Session(engine) as database:
        product = database.get(Product, product_id)
        assert product is not None
        assert product.stock_quantity == Decimal("7.000")
