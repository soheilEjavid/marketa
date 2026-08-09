"""One-off repair for two ledger drifts left behind by older code.

Both were found by auditing the live database against its own documents,
and both are history: the code paths that produced them are fixed, but the
rows they already wrote are still wrong and nothing recalculates them.

1. Invoices behind a balance payment. Until financials.py learned to settle
   open invoices oldest-first, a payment made against a customer's or
   supplier's overall balance moved only the balance. The invoices behind
   it stayed marked unpaid, so `party.balance` and the sum of that party's
   open invoices disagreed by exactly the amount ever paid that way.

2. Stock written without a movement. The demo seeder used to assign
   `Product.stock_quantity` directly when topping up a dead-stock line, so
   the shelf figure ran ahead of the sum of that product's inventory
   transactions — the ledger every other stock number is checked against.
   The ledger is the honest number here: it agrees line for line with the
   purchase and sale documents.

Reports only, unless you pass --apply:

    python -m app.repair_ledgers            # show what is wrong
    python -m app.repair_ledgers --apply    # fix it

Take a copy of the database first. --apply writes.
"""

from __future__ import annotations

import argparse
from decimal import Decimal

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.entities import (
    Customer,
    DocumentStatus,
    InventoryTransaction,
    InventoryTransactionType,
    Product,
    Purchase,
    Sale,
    Supplier,
)
from app.services.financials import _settle_oldest_first


def _repair_party_documents(database, *, apply: bool) -> int:
    """Re-run the oldest-first settlement over every party, using the
    balance as the authority for how much has been paid. `balance` is the
    figure that stayed correct throughout, because it was the only thing
    the old code updated.
    """
    repaired = 0

    for customer in database.scalars(select(Customer)):
        open_sales = list(database.scalars(
            select(Sale)
            .where(
                Sale.customer_id == customer.id,
                Sale.status == DocumentStatus.COMPLETED,
                Sale.remaining_amount > 0,
            )
            .order_by(Sale.created_at, Sale.id)
        ))
        outstanding = sum((sale.remaining_amount for sale in open_sales), Decimal("0"))
        unapplied = outstanding - customer.balance
        if unapplied <= 0:
            continue

        print(
            f"  customer {customer.id} {customer.full_name}: "
            f"balance {customer.balance:,} vs {outstanding:,} of open invoices "
            f"— {unapplied:,} to apply across {len(open_sales)} invoice(s)"
        )
        if apply:
            _settle_oldest_first(open_sales, unapplied)
        repaired += 1

    for supplier in database.scalars(select(Supplier)):
        open_purchases = list(database.scalars(
            select(Purchase)
            .where(
                Purchase.supplier_id == supplier.id,
                Purchase.status == DocumentStatus.COMPLETED,
                Purchase.remaining_amount > 0,
            )
            .order_by(Purchase.created_at, Purchase.id)
        ))
        outstanding = sum((p.remaining_amount for p in open_purchases), Decimal("0"))
        unapplied = outstanding - supplier.balance
        if unapplied <= 0:
            continue

        print(
            f"  supplier {supplier.id} {supplier.name}: "
            f"balance {supplier.balance:,} vs {outstanding:,} of open invoices "
            f"— {unapplied:,} to apply across {len(open_purchases)} invoice(s)"
        )
        if apply:
            _settle_oldest_first(open_purchases, unapplied)
        repaired += 1

    return repaired


def _repair_stock_ledger(database, *, apply: bool) -> int:
    """Post the missing movement as a real ADJUSTMENT row rather than
    editing the shelf figure to match: an unexplained gap is itself a fact
    about the stockroom, and a stocktake correction is exactly how a shop
    would record one.
    """
    ledger_totals = {
        product_id: total
        for product_id, total in database.execute(
            select(
                InventoryTransaction.product_id,
                func.coalesce(func.sum(InventoryTransaction.quantity_change), 0),
            ).group_by(InventoryTransaction.product_id)
        ).all()
    }

    repaired = 0
    for product in database.scalars(select(Product)):
        ledgered = Decimal(str(ledger_totals.get(product.id, 0)))
        gap = product.stock_quantity - ledgered
        if gap == 0:
            continue

        print(
            f"  product {product.id} {product.name}: "
            f"shelf {product.stock_quantity} vs ledger {ledgered} — posting {gap:+}"
        )
        if apply:
            database.add(
                InventoryTransaction(
                    product_id=product.id,
                    quantity_change=gap,
                    transaction_type=InventoryTransactionType.ADJUSTMENT,
                    related_id=None,
                )
            )
        repaired += 1

    return repaired


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write the repairs (default is a dry run)")
    args = parser.parse_args()

    with SessionLocal() as database:
        print("Invoices left unpaid behind a balance payment")
        parties = _repair_party_documents(database, apply=args.apply)
        if parties == 0:
            print("  nothing to repair")

        print("\nStock that moved without a ledger entry")
        products = _repair_stock_ledger(database, apply=args.apply)
        if products == 0:
            print("  nothing to repair")

        if args.apply:
            database.commit()
            print(f"\nApplied: {parties} party ledger(s), {products} product(s).")
        else:
            print(f"\nDry run: {parties} party ledger(s), {products} product(s) would change.")
            print("Re-run with --apply to write, after taking a copy of the database.")


if __name__ == "__main__":
    main()
