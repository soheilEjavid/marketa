"""One-off: blend the cost of products that were dual-priced before the
weighted-average change.

Those products carry `purchase_price` = the newer batch's price and
`old_purchase_price` = the earlier one. Under the old rule that was the
cost basis for everything on the shelf, including the units left from the
cheaper batch — so their cost reads high, their margin reads low, and the
inventory valuation is inflated.

Nothing fixes this on its own. The next delivery blends *from the current
figure*, so a wrong base is diluted but never cleared.

Idempotent by construction: it only touches products that are still
dual-priced and still carry an `old_purchase_price`, and it clears that
field as it goes. A second run finds nothing to do.

    python -m app.repair_dual_price_cost            # show what would change
    python -m app.repair_dual_price_cost --apply    # write it

Take a copy of the database first. --apply writes.
"""

from __future__ import annotations

import argparse
from decimal import Decimal

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.entities import Product
from app.services.products import weighted_average_cost


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write the repair (default is a dry run)")
    args = parser.parse_args()

    with SessionLocal() as database:
        products = list(database.scalars(
            select(Product).where(
                Product.is_dual_priced.is_(True),
                Product.old_purchase_price.is_not(None),
            )
        ))
        if not products:
            print("Nothing to repair — no dual-priced product still carries a separate old cost.")
            return

        print(f"{'product':<28}{'stock':>9}{'old batch':>11}{'cost now':>13}{'blended':>13}{'change':>9}")
        print("─" * 83)
        value_before = value_after = Decimal("0")
        for product in products:
            stock = Decimal(str(product.stock_quantity))
            # old_price_stock_estimate is how many of the earlier batch are
            # believed to be left; the rest of the shelf is the newer one.
            old_units = min(stock, Decimal(str(product.old_price_stock_estimate or 0)))
            new_units = max(Decimal("0"), stock - old_units)
            old_cost = Decimal(str(product.old_purchase_price))
            new_cost = Decimal(str(product.purchase_price))

            blended = weighted_average_cost(old_units, old_cost, new_units, new_cost)
            change = (blended - new_cost) / new_cost * 100 if new_cost else Decimal("0")
            value_before += stock * new_cost
            value_after += stock * blended
            print(f"{product.name[:27]:<28}{stock:>9}{old_units:>11}"
                  f"{new_cost:>13,.0f}{blended:>13,.0f}{change:>8.1f}%")

            if args.apply:
                product.purchase_price = blended
                # The earlier batch's cost has been folded in; keeping it
                # would let a later run blend it a second time.
                product.old_purchase_price = None

        print("─" * 83)
        print(f"{'inventory value of these lines':<28}{value_before:>24,.0f}{value_after:>13,.0f}"
              f"{(value_after - value_before) / value_before * 100:>8.1f}%")

        if args.apply:
            database.commit()
            print(f"\nApplied to {len(products)} product(s).")
        else:
            print(f"\nDry run: {len(products)} product(s) would change. "
                  "Re-run with --apply after taking a copy of the database.")


if __name__ == "__main__":
    main()
