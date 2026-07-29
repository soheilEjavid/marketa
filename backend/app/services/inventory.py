from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    InventoryTransaction,
    InventoryTransactionType,
    Product,
)


def list_transactions(
    database: Session,
    *,
    product_id: int | None = None,
    transaction_type: InventoryTransactionType | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[dict]:
    query = (
        select(InventoryTransaction, Product.name)
        .join(Product)
        .order_by(InventoryTransaction.timestamp.desc(), InventoryTransaction.id.desc())
        .offset(offset)
        .limit(limit)
    )
    if product_id is not None:
        query = query.where(InventoryTransaction.product_id == product_id)
    if transaction_type is not None:
        query = query.where(
            InventoryTransaction.transaction_type == transaction_type
        )

    return [
        {
            "id": transaction.id,
            "product_id": transaction.product_id,
            "product_name": product_name,
            "quantity_change": transaction.quantity_change,
            "transaction_type": transaction.transaction_type,
            "related_id": transaction.related_id,
            "timestamp": transaction.timestamp,
        }
        for transaction, product_name in database.execute(query)
    ]
