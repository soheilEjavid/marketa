from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import (
    CheckStatus,
    Customer,
    CustomerPayment,
    DocumentStatus,
    InventoryTransaction,
    InventoryTransactionType,
    LoyaltyPointTransaction,
    LoyaltyTransactionType,
    PaymentMethod,
    Product,
    Purchase,
    PurchaseItem,
    Sale,
    SaleItem,
    SalePaymentLine,
    Supplier,
    SupplierPayment,
)
from app.services.financials import payment_status


class AdjustmentError(ValueError):
    pass


class ProductNotFoundError(AdjustmentError):
    pass


def _money(value: Decimal) -> Decimal:
    """Every monetary column in this app is Numeric(14, 2); pro-rating a
    partial return produces thirds and sevenths, so round once here rather
    than letting the database truncate and leave the totals a rial adrift."""
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def adjust_stock(
    database: Session,
    product_id: int,
    quantity_change: Decimal,
    reason: str | None = None,
) -> Product:
    """Adjust stock for a product. Positive = increase, negative = decrease
    (spoilage, breakage, theft, a miscount found during a stocktake).
    Creates an inventory transaction with type ADJUSTMENT.

    Deliberately has no financial effect: the shop is out the *cost* of
    goods written off here, but there is nowhere honest to post that yet —
    Expense carries a cash/bank payment method and is subtracted from the
    till by shifts.py::close_shift, so booking a write-off as an expense
    would invent a cash shortage that never happened. Valuing shrinkage
    into net profit needs its own non-cash cost record; until then this
    moves stock only, and the loss shows up as unexplained margin.
    """
    product = database.get(Product, product_id)
    if product is None or not product.is_active:
        raise ProductNotFoundError(f"Product {product_id} not found or inactive")

    if quantity_change == 0:
        raise AdjustmentError("A stock adjustment cannot be zero")

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


def _claw_back_points(database: Session, customer: Customer, sale: Sale, credited: Decimal, original_total: Decimal) -> None:
    """Take back the share of this sale's loyalty points that the returned
    goods had earned. Points are awarded per payment against the invoice
    total (see loyalty.py::award_points_for_payment), so the honest
    reversal is proportional to how much of that total is being credited
    back. Capped at the customer's current balance — points already spent
    on another purchase cannot be un-spent, and the program's own rule is
    that a balance never goes negative.
    """
    if original_total <= 0 or credited <= 0:
        return

    earned_here = database.scalar(
        select(func.coalesce(func.sum(LoyaltyPointTransaction.points), 0)).where(
            LoyaltyPointTransaction.sale_id == sale.id,
            LoyaltyPointTransaction.transaction_type == LoyaltyTransactionType.EARN,
        )
    ) or 0
    if earned_here <= 0:
        return

    share = min(Decimal("1"), credited / original_total)
    clawback = min(int(Decimal(earned_here) * share), customer.loyalty_points_balance)
    if clawback <= 0:
        return

    customer.loyalty_points_balance -= clawback
    database.add(
        LoyaltyPointTransaction(
            customer_id=customer.id,
            points=-clawback,
            transaction_type=LoyaltyTransactionType.ADJUST,
            sale_id=sale.id,
            reason=f"برگشت از فروش فاکتور {sale.invoice_number}",
        )
    )


def return_sale_items(
    database: Session,
    sale_id: int,
    items: list[dict],
    *,
    refund_method: PaymentMethod | str = PaymentMethod.CASH,
) -> Sale:
    """Return specific items from a completed sale — a real credit note, not
    just a stock movement.

    Returning goods reverses everything the sale created for them: the
    line's revenue, its share of the invoice discount, its cost of goods
    (so reported profit drops with it), the customer's balance, the money
    itself, and the loyalty points it earned. Before this, a return put the
    goods back on the shelf and left the sale untouched, so the shop kept
    booking revenue and profit on merchandise standing in its own stockroom.

    The reversal is applied to the invoice in place, the way edit_sale()
    already amends a sale, rather than as a separate credit-note document:
    every report in this app reads revenue and cost straight off
    Sale/SaleItem, so amending them is what makes the dashboard, the sales
    report and net profit all tell the truth at once. The route records an
    audit entry, which is where the history of the change lives.

    Items format: [{"product_id": int, "quantity": Decimal, "reason": str | None}]
    """
    sale = database.get(Sale, sale_id)
    if sale is None:
        raise AdjustmentError(f"Sale {sale_id} not found")
    if sale.status != DocumentStatus.COMPLETED:
        raise AdjustmentError(f"Sale {sale_id} is not completed (status: {sale.status})")

    requested: dict[int, Decimal] = {}
    for item in items:
        quantity = Decimal(str(item["quantity"]))
        if quantity <= 0:
            raise AdjustmentError("A returned quantity must be greater than zero")
        requested[item["product_id"]] = requested.get(item["product_id"], Decimal("0")) + quantity

    original_total = sale.total
    lines_by_product: dict[int, SaleItem] = {line.product_id: line for line in sale.items}
    credited = Decimal("0")

    try:
        for product_id, quantity in requested.items():
            product = database.get(Product, product_id)
            if product is None or not product.is_active:
                raise ProductNotFoundError(f"Product {product_id} not found or inactive")

            line = lines_by_product.get(product_id)
            if line is None:
                raise AdjustmentError(f"Product {product_id} was not in sale {sale_id}")

            # The line's *current* quantity already has earlier returns taken
            # off it, so this one check also bounds the running total across
            # repeated returns against the same invoice. Without it, an
            # invoice that sold two units happily accepted five hundred back.
            if quantity > line.quantity:
                raise AdjustmentError(
                    f"Cannot return {quantity} of {product.name}: only "
                    f"{line.quantity} remain on invoice {sale.invoice_number}"
                )

            remaining_quantity = line.quantity - quantity
            # Pro-rate the line's own discount so the credit reflects what the
            # customer actually paid for these units, not the list price.
            if remaining_quantity > 0:
                new_discount = _money(line.discount * (remaining_quantity / line.quantity))
                new_line_total = _money(line.unit_price * remaining_quantity - new_discount)
            else:
                new_discount = Decimal("0")
                new_line_total = Decimal("0")

            credited += line.line_total - new_line_total

            line.quantity = remaining_quantity
            line.discount = new_discount
            line.line_total = new_line_total

            product.stock_quantity += quantity
            database.add(
                InventoryTransaction(
                    product_id=product.id,
                    quantity_change=quantity,
                    transaction_type=InventoryTransactionType.ADJUSTMENT,
                    related_id=sale.id,
                )
            )

            if remaining_quantity == 0:
                database.delete(line)

        database.flush()

        # ── Restate the invoice ──────────────────────────────────────────
        old_subtotal = sale.subtotal
        remaining_lines = [line for line in sale.items if line.quantity > 0]
        sale.subtotal = sum((line.line_total for line in remaining_lines), Decimal("0"))
        # The invoice-level discount rides along proportionally: a 10%-off
        # basket that is half returned is still 10% off what's left of it.
        if old_subtotal > 0 and sale.discount > 0:
            sale.discount = _money(sale.discount * (sale.subtotal / old_subtotal))
        sale.total = sale.subtotal - sale.discount
        credited = original_total - sale.total

        # ── Give the money back ──────────────────────────────────────────
        # Whatever they had already handed over comes back as cash now; the
        # rest simply stops being owed. min() splits the credit between those
        # two exactly, which is why a fully-paid sale refunds in full and an
        # unpaid credit sale refunds nothing but clears the debt.
        refund = min(credited, sale.paid_amount)
        if refund > 0:
            resolved_method = PaymentMethod(refund_method)
            sale.paid_amount -= refund
            database.add(
                SalePaymentLine(
                    sale=sale,
                    amount=-refund,
                    method=resolved_method,
                    notes=f"برگشت از فروش — فاکتور {sale.invoice_number}",
                    check_status=CheckStatus.PENDING if resolved_method == PaymentMethod.CHECK else None,
                )
            )
        sale.remaining_amount = sale.total - sale.paid_amount
        sale.payment_status = payment_status(sale.total, sale.paid_amount)

        if sale.customer_id:
            customer = database.get(Customer, sale.customer_id)
            if customer:
                # The sale put `total` on their account and each payment took
                # some off; undo both sides by the same amounts.
                customer.balance += refund - credited
                if refund > 0:
                    database.add(
                        CustomerPayment(
                            customer=customer,
                            sale=sale,
                            amount=-refund,
                            method=PaymentMethod(refund_method),
                            reference=f"{sale.invoice_number}-RETURN",
                            notes="برگشت از فروش",
                        )
                    )
                _claw_back_points(database, customer, sale, credited, original_total)

        # Nothing left on the invoice means the sale never really happened.
        # Cancelling keeps it out of revenue and off the sales history while
        # preserving the invoice number and its audit trail.
        if not remaining_lines:
            sale.status = DocumentStatus.CANCELLED

        database.commit()
    except Exception:
        database.rollback()
        raise

    database.refresh(sale)
    return sale


def return_purchase_items(
    database: Session,
    purchase_id: int,
    items: list[dict],
    *,
    refund_method: PaymentMethod | str = PaymentMethod.CASH,
) -> Purchase:
    """Send specific items back to a supplier — the mirror of
    return_sale_items(), and previously carrying the same hole: the goods
    left the stockroom but the shop went on owing for them.

    Reverses the line's cost from the invoice, reduces what is owed, and
    takes back any money already paid for those goods as a negative
    supplier payment (which shifts.py::close_shift reads as cash coming
    back into the till).
    """
    purchase = database.get(Purchase, purchase_id)
    if purchase is None:
        raise AdjustmentError(f"Purchase {purchase_id} not found")
    if purchase.status != DocumentStatus.COMPLETED:
        raise AdjustmentError(f"Purchase {purchase_id} is not completed")

    requested: dict[int, Decimal] = {}
    for item in items:
        quantity = Decimal(str(item["quantity"]))
        if quantity <= 0:
            raise AdjustmentError("A returned quantity must be greater than zero")
        requested[item["product_id"]] = requested.get(item["product_id"], Decimal("0")) + quantity

    lines_by_product: dict[int, PurchaseItem] = {line.product_id: line for line in purchase.items}
    credited = Decimal("0")

    try:
        for product_id, quantity in requested.items():
            product = database.get(Product, product_id)
            if product is None or not product.is_active:
                raise ProductNotFoundError(f"Product {product_id} not found or inactive")

            line = lines_by_product.get(product_id)
            if line is None:
                raise AdjustmentError(f"Product {product_id} was not in purchase {purchase_id}")

            if quantity > line.quantity:
                raise AdjustmentError(
                    f"Cannot return {quantity} of {product.name}: only "
                    f"{line.quantity} remain on purchase {purchase.invoice_number}"
                )
            if product.stock_quantity - quantity < 0:
                raise AdjustmentError(
                    f"Insufficient stock to return purchase item: "
                    f"{product.stock_quantity} available, need {quantity}"
                )

            remaining_quantity = line.quantity - quantity
            new_line_total = _money(line.unit_cost * remaining_quantity)
            credited += line.line_total - new_line_total

            line.quantity = remaining_quantity
            line.line_total = new_line_total

            product.stock_quantity -= quantity
            database.add(
                InventoryTransaction(
                    product_id=product.id,
                    quantity_change=-quantity,
                    transaction_type=InventoryTransactionType.ADJUSTMENT,
                    related_id=purchase.id,
                )
            )

            if remaining_quantity == 0:
                database.delete(line)

        database.flush()

        remaining_lines = [line for line in purchase.items if line.quantity > 0]
        purchase.total = sum((line.line_total for line in remaining_lines), Decimal("0"))

        refund = min(credited, purchase.paid_amount)
        if refund > 0:
            resolved_method = PaymentMethod(refund_method)
            purchase.paid_amount -= refund
            database.add(
                SupplierPayment(
                    supplier_id=purchase.supplier_id,
                    purchase=purchase,
                    amount=-refund,
                    method=resolved_method,
                    reference=f"{purchase.invoice_number}-RETURN",
                    notes="برگشت از خرید",
                    check_status=CheckStatus.PENDING if resolved_method == PaymentMethod.CHECK else None,
                )
            )
        purchase.remaining_amount = purchase.total - purchase.paid_amount
        purchase.payment_status = payment_status(purchase.total, purchase.paid_amount)

        if purchase.supplier_id:
            supplier = database.get(Supplier, purchase.supplier_id)
            if supplier:
                supplier.balance += refund - credited

        if not remaining_lines:
            purchase.status = DocumentStatus.CANCELLED

        database.commit()
    except Exception:
        database.rollback()
        raise

    database.refresh(purchase)
    return purchase
