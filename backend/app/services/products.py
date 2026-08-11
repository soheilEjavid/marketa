from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import InventoryTransaction, InventoryTransactionType, Product
from app.schemas.product import ProductCreate, ProductUpdate
from app.services.audit import record_audit


class DuplicateBarcodeError(ValueError):
    pass


class DuplicateSkuError(ValueError):
    pass


def _raise_for_integrity_error(error: IntegrityError) -> None:
    message = str(getattr(error, "orig", error))
    if "sku" in message.lower():
        raise DuplicateSkuError("SKU is already in use") from error
    raise DuplicateBarcodeError("Barcode is already in use") from error


def list_products(
    database: Session,
    *,
    search: str | None = None,
    category_id: int | None = None,
    active_only: bool = True,
    offset: int = 0,
    limit: int = 100,
) -> list[Product]:
    query = select(Product).order_by(Product.name).offset(offset).limit(limit)
    if active_only:
        query = query.where(Product.is_active.is_(True))
    if category_id is not None:
        query = query.where(Product.category_id == category_id)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(
            or_(
                Product.name.ilike(pattern),
                Product.barcode.ilike(pattern),
                Product.brand.ilike(pattern),
                Product.sku.ilike(pattern),
            )
        )
    return list(database.scalars(query))


def get_product(database: Session, product_id: int) -> Product | None:
    return database.get(Product, product_id)


def create_product(database: Session, data: ProductCreate) -> Product:
    """Add a product, logging any opening stock as a real movement.

    A brand-new product may be entered with stock already on the shelf —
    a shopkeeper typing up what they have. That quantity used to be written
    straight to `Product.stock_quantity` with nothing in the inventory
    ledger to account for it, on the reasoning that a new product has no
    history to log against.

    It does have one: the units exist. And `stock == Σ inventory movements`
    is the invariant the whole financial audit rests on, so every product
    entered that way left a gap the audit reports as an unexplained
    difference. Worse than the noise itself is what it teaches — once
    unexplained differences are normal, a real one gets waved through as
    "just another opening balance". Setting up a shop with five hundred
    products would have opened five hundred of them.
    """
    product = Product(**data.model_dump())
    database.add(product)
    try:
        database.flush()
        opening = Decimal(str(product.stock_quantity or 0))
        if opening != 0:
            # The cost basis of these units is Product.purchase_price, set
            # on the same row — an InventoryTransaction carries a quantity
            # and nothing else, which is why the guard below matters.
            database.add(
                InventoryTransaction(
                    product_id=product.id,
                    quantity_change=opening,
                    transaction_type=InventoryTransactionType.ADJUSTMENT,
                    related_id=None,
                )
            )
        database.commit()
    except IntegrityError as error:
        database.rollback()
        _raise_for_integrity_error(error)
    database.refresh(product)
    return product


def update_product(
    database: Session, product: Product, data: ProductUpdate
) -> Product:
    dump = data.model_dump(exclude_unset=True)

    # ── Handle collapse_to_tier (manager collapsing dual-price) ──────
    collapse_tier = dump.pop("collapse_to_tier", None)
    if collapse_tier and product.is_dual_priced:
        if collapse_tier == "old":
            # Keep old prices as the single ongoing price
            product.purchase_price = product.old_purchase_price
            product.sale_price = product.old_sale_price
        # else "new" — keep existing prices (they already represent the new tier)
        product.is_dual_priced = False
        product.old_purchase_price = None
        product.old_sale_price = None
        product.old_price_stock_estimate = None
        product.dual_price_started_at = None
        # We'll log the action after applying remaining field updates

    for field, value in dump.items():
        setattr(product, field, value)

    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        _raise_for_integrity_error(error)
    database.refresh(product)
    return product


def deactivate_product(database: Session, product: Product) -> Product:
    product.is_active = False
    database.commit()
    database.refresh(product)
    return product


def weighted_average_cost(
    current_stock: Decimal,
    current_cost: Decimal,
    incoming_quantity: Decimal,
    incoming_cost: Decimal,
) -> Decimal:
    """The cost of one unit once a delivery is mixed into what is on hand.

        (stock × cost + delivered × delivered_cost) / (stock + delivered)

    Replacing the cost outright — what this used to do — says every unit on
    the shelf was bought at the newest price, which is only true when the
    shelf was empty. With stock left over from a cheaper batch it overstates
    what the goods cost, understates margin, and inflates the inventory
    valuation. That error is not confined to dual-priced products; it
    applies to any restock at a new price with stock still on hand.

    Negative or zero stock falls back to the delivered price: there is
    nothing to average against, and a negative figure would produce a
    nonsense weight.
    """
    if current_stock <= 0:
        return _money(incoming_cost)
    if incoming_quantity <= 0:
        return _money(current_cost)
    total_units = current_stock + incoming_quantity
    blended = (current_stock * current_cost + incoming_quantity * incoming_cost) / total_units
    return _money(blended)


def _money(value: Decimal) -> Decimal:
    """Money is Numeric(14, 2) throughout; a blended cost lands on thirds."""
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ── Dual-price helpers ─────────────────────────────────────────────────────


def enable_dual_pricing(
    database: Session,
    product: Product,
    new_purchase_price: Decimal,
    new_sale_price: Decimal,
    *,
    incoming_quantity: Decimal = Decimal("0"),
    old_price_stock_estimate: Decimal | None = None,
    user_id: int | None = None,
    username: str | None = None,
    commit: bool = True,
) -> Product:
    """Move current prices to old_* fields and set new prices, entering
    dual-price mode.

    `commit=False` for callers inside a larger transaction — the same
    convention financials.record_customer_payment() follows.
    purchases._apply_dual_pricing() runs this from inside process_purchase(),
    *before* the Purchase row exists, so committing here persisted the price
    split on its own: a delivery that then failed its overpayment guard left
    the product dual-priced with prices from goods that never arrived, no
    purchase recorded, and an audit row for an event that did not happen.
    """
    # The sale side genuinely splits in two: the old batch keeps its price
    # on the shelf. The cost side does not — those units are mixed in the
    # stockroom and carry one blended cost from here on. old_purchase_price
    # is kept only as a record of what the earlier batch cost; nothing reads
    # it as a cost basis any more (see services/sales.py).
    product.old_purchase_price = product.purchase_price
    product.old_sale_price = product.sale_price
    product.purchase_price = weighted_average_cost(
        product.stock_quantity, product.purchase_price,
        incoming_quantity, new_purchase_price,
    )
    product.sale_price = new_sale_price
    product.is_dual_priced = True
    product.dual_price_started_at = datetime.now(UTC)
    if old_price_stock_estimate is not None:
        product.old_price_stock_estimate = old_price_stock_estimate
    if commit:
        database.commit()
        database.refresh(product)
    else:
        # The caller owns the transaction; make the new values visible to
        # the rest of it without ending it.
        database.flush()

    record_audit(
        database,
        commit=commit,
        user_id=user_id,
        username=username,
        action="enable_dual_pricing",
        entity_type="product",
        entity_id=product.id,
        details=(
            f"Dual-price enabled: old purchase={product.old_purchase_price}, "
            f"old sale={product.old_sale_price}, "
            f"new purchase={product.purchase_price}, new sale={product.sale_price}"
        ),
    )
    return product


def collapse_dual_pricing(
    database: Session,
    product: Product,
    keep_tier: str,
    *,
    user_id: int | None = None,
    username: str | None = None,
) -> Product:
    """Collapse a dual-priced product back to a single price, keeping the specified tier."""
    # Only the *sale* price has two tiers to choose between. Cost is a
    # single blended figure and collapsing a marketing decision must not
    # rewrite it — picking the old tier here used to drag purchase_price
    # back to the earlier batch's price, discarding the blend.
    if keep_tier == "old":
        product.sale_price = product.old_sale_price
    # else "new" — keep the current sale price as-is

    product.is_dual_priced = False
    old_purchase = product.old_purchase_price
    old_sale = product.old_sale_price
    product.old_purchase_price = None
    product.old_sale_price = None
    product.old_price_stock_estimate = None
    product.dual_price_started_at = None

    database.commit()
    database.refresh(product)

    record_audit(
        database,
        user_id=user_id,
        username=username,
        action="collapse_dual_pricing",
        entity_type="product",
        entity_id=product.id,
        details=(
            f"Collapsed dual-price, kept '{keep_tier}' tier. "
            f"Old tier was: purchase={old_purchase}, sale={old_sale}. "
            f"Final: purchase={product.purchase_price}, sale={product.sale_price}"
        ),
    )
    return product


def decrement_old_stock_estimate(
    database: Session, product: Product, quantity: Decimal, *, commit: bool = True
) -> None:
    """Draw `quantity` down from the informational old-stock estimate.

    `quantity` is what was actually sold on the old tier. This used to
    subtract a flat 1 per invoice *line* regardless — selling 5 of something
    moved the estimate by 1, so the figure drifted further from reality with
    every multi-unit sale and always read high. For a weighted product it
    could not work at all: 2.350 kg does not round to "one".

    `commit=False` is required whenever this is called from inside a larger
    transaction — same convention as financials.record_customer_payment().
    Committing here mid-sale used to persist the caller's half-built sale:
    _build_sale_items() adds the SaleItem and decrements stock *before*
    calling this, and only adds the matching InventoryTransaction *after*,
    so a commit in between wrote the stock change to disk while its ledger
    row was still pending and got rolled back with the rest of the failed
    sale. That left stock silently missing with nothing to explain it, plus
    an orphan `completed` invoice with a zero total.
    """
    if product.is_dual_priced and product.old_price_stock_estimate is not None:
        product.old_price_stock_estimate = max(
            Decimal("0"), Decimal(product.old_price_stock_estimate) - quantity
        )
        if commit:
            database.commit()
            database.refresh(product)

