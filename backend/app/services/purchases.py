import json
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    CheckStatus,
    DocumentStatus,
    PaymentMethod,
    Supplier,
    SupplierPayment,
    InventoryTransaction,
    InventoryTransactionType,
    Product,
    Purchase,
    PurchaseItem,
)
from app.schemas.purchase import PurchaseCreate, PurchaseEditRequest, PurchaseItemCreate, PurchasePaymentLineInput
from app.services.financials import payment_status
from app.services.products import enable_dual_pricing, weighted_average_cost


class PurchaseError(ValueError):
    pass


class ProductNotFoundError(PurchaseError):
    pass


class DuplicateInvoiceError(PurchaseError):
    pass


class DualPriceRequiredError(PurchaseError):
    """Raised when a purchase triggers a price change on a product with existing stock."""

    def __init__(self, products_info: list[dict]) -> None:
        self.products_info = products_info
        super().__init__("Dual-pricing confirmation required for some products")


def _invoice_number() -> str:
    date_part = datetime.now(UTC).strftime("%Y%m%d")
    return f"PUR-{date_part}-{uuid4().hex[:8].upper()}"


def _check_dual_pricing_needed(
    data: PurchaseCreate,
    products: dict[int, Product],
) -> list[dict]:
    """Check which products need dual-pricing confirmation. Returns list of product info dicts."""
    products_needing_dual: list[dict] = []
    for item_data in data.items:
        product = products[item_data.product_id]
        has_stock = product.stock_quantity > 0
        purchase_price_changed = item_data.unit_cost != product.purchase_price
        sale_price_changed = (
            item_data.selling_price is not None
            and item_data.selling_price != product.sale_price
        )
        price_changed = purchase_price_changed or sale_price_changed
        if has_stock and price_changed and not product.is_dual_priced:
            if item_data.selling_price is not None:
                suggested_new_sale_price = item_data.selling_price
            else:
                old_margin_pct = (
                    (product.sale_price - product.purchase_price) / product.purchase_price
                    if product.purchase_price > 0
                    else Decimal("0.25")
                )
                suggested_new_sale_price = item_data.unit_cost * (Decimal("1") + old_margin_pct)
                suggested_new_sale_price = (suggested_new_sale_price / 100).quantize(Decimal("1")) * 100

            products_needing_dual.append({
                "product_id": product.id,
                "product_name": product.name,
                "current_purchase_price": float(product.purchase_price),
                "current_sale_price": float(product.sale_price),
                "new_purchase_price": float(item_data.unit_cost),
                "suggested_new_sale_price": float(suggested_new_sale_price),
                "current_stock": float(product.stock_quantity),
                "purchase_price_changed": purchase_price_changed,
                "sale_price_changed": sale_price_changed,
            })
        elif has_stock and price_changed and product.is_dual_priced:
            products_needing_dual.append({
                "product_id": product.id,
                "product_name": product.name,
                "is_update_existing_dual": True,
                "current_purchase_price": float(product.purchase_price),
                "current_sale_price": float(product.sale_price),
                "new_purchase_price": float(item_data.unit_cost),
                "suggested_new_sale_price": float(
                    item_data.selling_price if item_data.selling_price is not None else product.sale_price
                ),
                "current_stock": float(product.stock_quantity),
                "purchase_price_changed": purchase_price_changed,
                "sale_price_changed": sale_price_changed,
            })
    return products_needing_dual


def _apply_dual_pricing(
    data: PurchaseCreate,
    products: dict[int, Product],
    database: Session,
) -> None:
    """Apply dual-pricing for confirmed products."""
    if data.confirm_dual_pricing and data.dual_pricing_new_sale_prices:
        for item_data in data.items:
            product = products[item_data.product_id]
            has_stock = product.stock_quantity > 0
            purchase_price_changed = item_data.unit_cost != product.purchase_price
            sale_price_changed = (
                item_data.selling_price is not None
                and item_data.selling_price != product.sale_price
            )
            price_changed = purchase_price_changed or sale_price_changed
            if has_stock and price_changed:
                new_sale_price = data.dual_pricing_new_sale_prices.get(
                    product.id, item_data.selling_price or product.sale_price
                )
                # commit=False: process_purchase() owns this transaction and
                # the Purchase row does not exist yet.
                enable_dual_pricing(
                    database,
                    product,
                    new_purchase_price=item_data.unit_cost,
                    new_sale_price=Decimal(str(new_sale_price)),
                    incoming_quantity=item_data.quantity,
                    commit=False,
                )


def _merge_duplicate_purchase_items(items: list[PurchaseItemCreate]) -> list[PurchaseItemCreate]:
    """Mirrors sales._merge_duplicate_sale_items -- see there for the full
    reasoning. Sums quantities for repeated product_id entries, keeping
    every other field (unit_cost, selling_price, expiry_date, and id when
    editing) from the first occurrence in submission order.
    Must run before _check_dual_pricing_needed()/_build_purchase_items() so
    neither sees the raw, unmerged duplicate lines.
    """
    merged: dict[int, PurchaseItemCreate] = {}
    order: list[int] = []
    for item in items:
        if item.product_id in merged:
            existing = merged[item.product_id]
            merged[item.product_id] = existing.model_copy(update={"quantity": existing.quantity + item.quantity})
        else:
            merged[item.product_id] = item
            order.append(item.product_id)
    return [merged[product_id] for product_id in order]


def _build_purchase_items(
    database: Session,
    purchase: Purchase,
    data: PurchaseCreate,
    products: dict[int, Product],
) -> Decimal:
    """Create PurchaseItem rows, adjust stock, and return the payable total."""
    total = Decimal("0")
    for item_data in data.items:
        product = products[item_data.product_id]
        line_total = item_data.quantity * item_data.unit_cost
        database.add(
            PurchaseItem(
                purchase_id=purchase.id,
                product_id=product.id,
                quantity=item_data.quantity,
                unit_cost=item_data.unit_cost,
                selling_price=item_data.selling_price,
                expiry_date=item_data.expiry_date,
                line_total=line_total,
            )
        )
        # Blend before the stock moves: the weighting needs what was on the
        # shelf *before* this delivery landed on it.
        if not product.is_dual_priced:
            product.purchase_price = weighted_average_cost(
                product.stock_quantity, product.purchase_price,
                item_data.quantity, item_data.unit_cost,
            )
            if item_data.selling_price is not None:
                product.sale_price = item_data.selling_price
        product.stock_quantity += item_data.quantity
        database.add(
            InventoryTransaction(
                product_id=product.id,
                quantity_change=item_data.quantity,
                transaction_type=InventoryTransactionType.PURCHASE,
                related_id=purchase.id,
            )
        )
        total += line_total
    return total


def _apply_payment_line(
    database: Session,
    purchase: Purchase,
    supplier: Supplier | None,
    line: PurchasePaymentLineInput,
) -> None:
    """Record one payment line against a purchase, updating its running
    paid/remaining totals and (when a supplier is on file) the supplier's
    balance. Overpay is guarded by the caller, which checks the line sum
    against the invoice total before any line is applied.
    """
    database.add(
        SupplierPayment(
            supplier=supplier,
            purchase=purchase,
            amount=line.amount,
            method=PaymentMethod(line.method),
            notes=line.notes,
            check_number=line.check_number,
            check_bank_name=line.check_bank_name,
            check_due_date=line.check_due_date,
            check_status=CheckStatus.PENDING if line.method == "check" else None,
        )
    )
    purchase.paid_amount += line.amount
    purchase.remaining_amount = purchase.total - purchase.paid_amount
    purchase.payment_status = payment_status(purchase.total, purchase.paid_amount)
    if supplier:
        supplier.balance = max(Decimal("0"), supplier.balance - line.amount)


def _purchase_item_snapshot(item: PurchaseItem) -> dict:
    return {
        "id": item.id,
        "product_id": item.product_id,
        "quantity": str(item.quantity),
        "unit_cost": str(item.unit_cost),
        "selling_price": str(item.selling_price) if item.selling_price is not None else None,
    }


def process_purchase(database: Session, data: PurchaseCreate) -> Purchase:
    data.items = _merge_duplicate_purchase_items(data.items)
    product_ids = {item.product_id for item in data.items}

    try:
        products = {
            product.id: product
            for product in database.scalars(
                select(Product)
                .where(Product.id.in_(product_ids), Product.is_active.is_(True))
                .with_for_update()
            )
        }
        missing_ids = product_ids - set(products)
        if missing_ids:
            raise ProductNotFoundError(
                f"Products not found or inactive: {sorted(missing_ids)}"
            )

        supplier = database.get(Supplier, data.supplier_id) if data.supplier_id else None
        if data.supplier_id and (supplier is None or not supplier.is_active):
            raise PurchaseError("Supplier not found or inactive")

        # Check for products needing dual-pricing confirmation
        if not data.confirm_dual_pricing:
            products_needing_dual = _check_dual_pricing_needed(data, products)
            if products_needing_dual:
                raise DualPriceRequiredError(products_needing_dual)

        # Apply dual-pricing if confirmed
        _apply_dual_pricing(data, products, database)

        purchase = Purchase(
            invoice_number=data.invoice_number or _invoice_number(),
            supplier_id=data.supplier_id,
            paid_amount=Decimal("0"),
            status=DocumentStatus.COMPLETED,
            notes=data.notes,
        )
        database.add(purchase)
        database.flush()

        total = _build_purchase_items(database, purchase, data, products)

        purchase.total = total
        paid_total = sum((line.amount for line in data.payment_lines), Decimal("0"))
        if paid_total > total:
            raise PurchaseError("Paid amount cannot exceed the purchase total")

        purchase.paid_amount = Decimal("0")
        purchase.remaining_amount = total
        purchase.payment_status = payment_status(total, Decimal("0"))

        if supplier:
            supplier.balance += total
            supplier.last_purchase_at = datetime.now(UTC)

        for line in data.payment_lines:
            _apply_payment_line(database, purchase, supplier, line)

        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise DuplicateInvoiceError("Invoice number is already in use") from error
    except Exception:
        database.rollback()
        raise

    return database.scalar(
        select(Purchase)
        .where(Purchase.id == purchase.id)
        .options(selectinload(Purchase.items), selectinload(Purchase.payment_lines))
    )


def edit_purchase(database: Session, purchase: Purchase, data: PurchaseEditRequest) -> tuple[Purchase, str]:
    """Edit an existing purchase's line items.

    Computes per-line stock/cost deltas rather than reversing and rebuilding
    the whole purchase from scratch. Blocks entirely if any referenced
    product currently has an active dual-price state (see task write-up —
    the correct cascade there is genuinely ambiguous, so we refuse rather
    than guess). Only updates the product's *live* purchase/sale price when
    this purchase is the most recent one on record for that product;
    otherwise only this invoice's own recorded values change.
    """
    if purchase.status == DocumentStatus.CANCELLED:
        raise PurchaseError("Cannot edit a cancelled purchase")

    data.items = _merge_duplicate_purchase_items(data.items)
    old_items_by_id: dict[int, PurchaseItem] = {item.id: item for item in purchase.items}
    new_item_ids = {item.id for item in data.items if item.id is not None}

    unknown_ids = new_item_ids - set(old_items_by_id)
    if unknown_ids:
        raise PurchaseError(f"Line item(s) {sorted(unknown_ids)} do not belong to this purchase")

    for item_data in data.items:
        if item_data.id is not None and old_items_by_id[item_data.id].product_id != item_data.product_id:
            raise PurchaseError(
                "Changing a line's product isn't supported — remove this line "
                "and add a new one instead"
            )

    removed_items = [item for item_id, item in old_items_by_id.items() if item_id not in new_item_ids]
    all_product_ids = {item.product_id for item in data.items} | {item.product_id for item in removed_items}

    try:
        products = {
            product.id: product
            for product in database.scalars(
                select(Product).where(Product.id.in_(all_product_ids)).with_for_update()
            )
        }
        missing_ids = all_product_ids - set(products)
        if missing_ids:
            raise ProductNotFoundError(f"Products not found: {sorted(missing_ids)}")

        # ── Refuse to touch a purchase tied to an active dual-price state —
        # see docstring; this is a deliberate block, not an oversight. ──
        dual_priced_names = [p.name for p in products.values() if p.is_dual_priced]
        if dual_priced_names:
            raise PurchaseError(
                "Cannot edit this purchase: "
                f"{', '.join(dual_priced_names)} currently has an active dual-price "
                "state. Collapse it to a single price first, then edit this invoice."
            )

        # ── Net stock delta per product (inverse direction vs. sales) ──
        stock_deltas: dict[int, Decimal] = defaultdict(Decimal)
        for item in removed_items:
            stock_deltas[item.product_id] -= item.quantity
        for item_data in data.items:
            if item_data.id is not None:
                old_item = old_items_by_id[item_data.id]
                stock_deltas[item_data.product_id] += item_data.quantity - old_item.quantity
            else:
                stock_deltas[item_data.product_id] += item_data.quantity

        for product_id, delta in stock_deltas.items():
            resulting = products[product_id].stock_quantity + delta
            if resulting < 0:
                raise PurchaseError(
                    f"Cannot reduce purchased quantity for {products[product_id].name}: "
                    f"some of it has already been sold or used elsewhere — "
                    f"this edit would leave stock at {resulting}"
                )

        old_snapshot = {
            "total": str(purchase.total),
            "items": [_purchase_item_snapshot(item) for item in purchase.items],
        }

        for product_id, delta in stock_deltas.items():
            if delta == 0:
                continue
            products[product_id].stock_quantity += delta
            database.add(
                InventoryTransaction(
                    product_id=product_id,
                    quantity_change=delta,
                    transaction_type=InventoryTransactionType.ADJUSTMENT,
                    related_id=purchase.id,
                )
            )

        for item in removed_items:
            database.delete(item)

        # ── "Most recent purchase" per affected product, by creation time —
        # only that purchase's edit is allowed to move the live price. ──
        latest_purchase_id_by_product: dict[int, int | None] = {}
        for product_id in all_product_ids:
            latest_purchase_id_by_product[product_id] = database.scalar(
                select(Purchase.id)
                .join(PurchaseItem, PurchaseItem.purchase_id == Purchase.id)
                .where(PurchaseItem.product_id == product_id)
                .order_by(Purchase.created_at.desc(), Purchase.id.desc())
                .limit(1)
            )

        total = Decimal("0")
        for item_data in data.items:
            product = products[item_data.product_id]
            line_total = item_data.quantity * item_data.unit_cost
            if item_data.id is not None:
                line = old_items_by_id[item_data.id]
                line.quantity = item_data.quantity
                line.unit_cost = item_data.unit_cost
                line.selling_price = item_data.selling_price
                line.expiry_date = item_data.expiry_date
                line.line_total = line_total
            else:
                database.add(
                    PurchaseItem(
                        purchase_id=purchase.id,
                        product_id=product.id,
                        quantity=item_data.quantity,
                        unit_cost=item_data.unit_cost,
                        selling_price=item_data.selling_price,
                        expiry_date=item_data.expiry_date,
                        line_total=line_total,
                    )
                )
            total += line_total

            if latest_purchase_id_by_product.get(item_data.product_id) == purchase.id:
                product.purchase_price = item_data.unit_cost
                if item_data.selling_price is not None:
                    product.sale_price = item_data.selling_price

        old_total = purchase.total
        purchase.total = total
        total_delta = purchase.total - old_total
        purchase.remaining_amount = purchase.remaining_amount + total_delta
        purchase.payment_status = payment_status(purchase.total, purchase.paid_amount)

        if purchase.supplier_id:
            supplier = database.get(Supplier, purchase.supplier_id)
            if supplier:
                supplier.balance += total_delta

        database.flush()
        new_snapshot = {
            "total": str(purchase.total),
            "items": [_purchase_item_snapshot(item) for item in purchase.items],
        }
        audit_details = json.dumps(
            {"reason": data.reason, "old": old_snapshot, "new": new_snapshot},
            ensure_ascii=False,
        )

        database.commit()
    except Exception:
        database.rollback()
        raise

    updated = database.scalar(
        select(Purchase).where(Purchase.id == purchase.id).options(selectinload(Purchase.items), selectinload(Purchase.payment_lines))
    )
    return updated, audit_details


def get_purchase(database: Session, purchase_id: int) -> Purchase | None:
    return database.scalar(
        select(Purchase)
        .where(Purchase.id == purchase_id)
        .options(selectinload(Purchase.items), selectinload(Purchase.payment_lines))
    )

def list_purchases(
    database: Session,
    *,
    search: str | None = None,
    sort: str = "date_desc",
    offset: int = 0,
    limit: int = 100,
) -> list[Purchase]:
    query = select(Purchase).options(selectinload(Purchase.items), selectinload(Purchase.payment_lines))
    if search:
        pattern = f"%{search.strip()}%"
        query = query.outerjoin(Supplier, Purchase.supplier_id == Supplier.id).where(
            or_(Purchase.invoice_number.ilike(pattern), Supplier.name.ilike(pattern))
        )
    query = query.order_by(Purchase.created_at.asc() if sort == "date_asc" else Purchase.created_at.desc())
    return list(database.scalars(query.offset(offset).limit(limit)))


def count_purchases(database: Session, *, search: str | None = None) -> int:
    from sqlalchemy import func

    query = select(func.count(Purchase.id))
    if search:
        pattern = f"%{search.strip()}%"
        query = query.select_from(Purchase).outerjoin(Supplier, Purchase.supplier_id == Supplier.id).where(
            or_(Purchase.invoice_number.ilike(pattern), Supplier.name.ilike(pattern))
        )
    return database.scalar(query) or 0