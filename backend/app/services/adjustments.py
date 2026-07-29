from datetime import datetime, UTC
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    DocumentStatus,
    InventoryTransaction,
    InventoryTransactionType,
    Product,
    Sale,
    SaleItem,
    Purchase,
    PurchaseItem,
)


class AdjustmentError(ValueError):
    pass


class ProductNotFoundError(AdjustmentError):
    pass


def adjust_stock(
    database: Session,
    product_id: int,
    quantity_change: Decimal,
    reason: str | None = None,
) -> Product:
    """Adjust stock for a product. Positive = increase, negative = decrease.
    Creates an inventory transaction with type ADJUSTMENT."""
    product = database.get(Product, product_id)
    if product is None or not product.is_active:
        raise ProductNotFoundError(f"Product {product_id} not found or inactive")

    if product.stock_quantity + quantity_change < 0:
        raise AdjustmentError(
            f"Insufficient stock: {product.stock_quantity} available, "
            f"cannot reduce by {abs(quantity_change)}"
        )

    product.stock_quantity += quantity_change
    database.add(
        InventoryTransaction(
            product_id=product.id,
            quantity_change=quantity_change,
            transaction_type=InventoryTransactionType.ADJUSTMENT,
            related_id=None,
        )
    )
    database.commit()
    database.refresh(product)
    return product


def return_sale_items(
    database: Session,
    sale_id: int,
    items: list[dict],
) -> Sale:
    """Return specific items from a completed sale. Increases stock and logs transactions.
    Items format: [{"product_id": int, "quantity": Decimal, "reason": str | None}]"""
    sale = database.get(Sale, sale_id)
    if sale is None:
        raise AdjustmentError(f"Sale {sale_id} not found")
    if sale.status != DocumentStatus.COMPLETED:
        raise AdjustmentError(f"Sale {sale_id} is not completed (status: {sale.status})")

    for item in items:
        product = database.get(Product, item["product_id"])
        if product is None or not product.is_active:
            raise ProductNotFoundError(f"Product {item['product_id']} not found or inactive")

        # Verify the product was in the original sale
        sale_item = database.scalar(
            select(SaleItem).where(
                SaleItem.sale_id == sale_id,
                SaleItem.product_id == item["product_id"],
            )
        )
        if sale_item is None:
            raise AdjustmentError(
                f"Product {item['product_id']} was not in sale {sale_id}"
            )

        quantity = item["quantity"]
        product.stock_quantity += quantity
        database.add(
            InventoryTransaction(
                product_id=product.id,
                quantity_change=quantity,
                transaction_type=InventoryTransactionType.ADJUSTMENT,
                related_id=sale.id,
            )
        )

    database.commit()
    database.refresh(sale)
    return sale


def return_purchase_items(
    database: Session,
    purchase_id: int,
    items: list[dict],
) -> Purchase:
    """Return specific items from a completed purchase. Decreases stock and logs transactions."""
    purchase = database.get(Purchase, purchase_id)
    if purchase is None:
        raise AdjustmentError(f"Purchase {purchase_id} not found")
    if purchase.status != DocumentStatus.COMPLETED:
        raise AdjustmentError(f"Purchase {purchase_id} is not completed")

    for item in items:
        product = database.get(Product, item["product_id"])
        if product is None or not product.is_active:
            raise ProductNotFoundError(f"Product {item['product_id']} not found or inactive")

        purchase_item = database.scalar(
            select(PurchaseItem).where(
                PurchaseItem.purchase_id == purchase_id,
                PurchaseItem.product_id == item["product_id"],
            )
        )
        if purchase_item is None:
            raise AdjustmentError(
                f"Product {item['product_id']} was not in purchase {purchase_id}"
            )

        quantity = item["quantity"]
        if product.stock_quantity - quantity < 0:
            raise AdjustmentError(
                f"Insufficient stock to return purchase item: "
                f"{product.stock_quantity} available, need {quantity}"
            )

        product.stock_quantity -= quantity
        database.add(
            InventoryTransaction(
                product_id=product.id,
                quantity_change=-quantity,
                transaction_type=InventoryTransactionType.ADJUSTMENT,
                related_id=purchase.id,
            )
        )

    database.commit()
    database.refresh(purchase)
    return purchase