"""One-off: log the opening stock that was never logged.

`create_product` used to write an opening quantity straight to
`Product.stock_quantity` with nothing in the inventory ledger. Products
entered that way read correctly on the shelf but leave the audit's
`stock == Σ movements` invariant short by exactly the opening amount.

This posts the missing movement as an ADJUSTMENT, which is what it always
was: units that appeared on the shelf without a purchase behind them.

Idempotent: the gap it repairs is measured, so once posted there is no gap
and a second run finds nothing. It never assumes a product is broken —
only ones whose two figures actually disagree are touched.

    python -m app.repair_opening_stock            # show what would change
    python -m app.repair_opening_stock --apply    # write it

Take a copy of the database first. --apply writes.
"""

from __future__ import annotations

import argparse
from decimal import Decimal

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.entities import InventoryTransaction, InventoryTransactionType, Product


def _ledger_total(database, product_id: int) -> Decimal:
    return Decimal(str(database.scalar(
        select(func.coalesce(func.sum(InventoryTransaction.quantity_change), 0))
        .where(InventoryTransaction.product_id == product_id)) or 0))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write the repair (default is a dry run)")
    args = parser.parse_args()

    with SessionLocal() as database:
        products = list(database.scalars(select(Product)))
        gaps = []
        for product in products:
            stock = Decimal(str(product.stock_quantity))
            gap = stock - _ledger_total(database, product.id)
            if gap != 0:
                gaps.append((product, stock, gap))

        if not gaps:
            print(f"Nothing to repair — all {len(products)} products agree with their ledger.")
            return

        print(f"{'product':<30}{'stock':>12}{'ledger':>12}{'missing':>12}{'cost basis':>14}")
        print("─" * 80)
        for product, stock, gap in gaps:
            print(f"{product.name[:29]:<30}{stock:>12}{stock - gap:>12}{gap:>+12}"
                  f"{Decimal(str(product.purchase_price)):>14,.0f}")
            if args.apply:
                database.add(
                    InventoryTransaction(
                        product_id=product.id,
                        quantity_change=gap,
                        transaction_type=InventoryTransactionType.ADJUSTMENT,
                        related_id=None,
                        # Backdated to when the product was entered — that is
                        # when the units appeared, and dating it today would
                        # put a phantom movement in this week's stock report.
                        timestamp=product.created_at,
                    )
                )

        print("─" * 80)
        print(f"{len(gaps)} of {len(products)} products affected.")

        if args.apply:
            database.commit()
            remaining = sum(
                1 for product in database.scalars(select(Product))
                if Decimal(str(product.stock_quantity)) != _ledger_total(database, product.id)
            )
            print(f"\nApplied. Products still disagreeing with their ledger: {remaining}")
        else:
            print("\nDry run. Re-run with --apply after taking a copy of the database.")


if __name__ == "__main__":
    main()
