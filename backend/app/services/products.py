from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import Product
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
    product = Product(**data.model_dump())
    database.add(product)
    try:
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


# ── Dual-price helpers ─────────────────────────────────────────────────────


def enable_dual_pricing(
    database: Session,
    product: Product,
    new_purchase_price: Decimal,
    new_sale_price: Decimal,
    *,
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
    product.old_purchase_price = product.purchase_price
    product.old_sale_price = product.sale_price
    product.purchase_price = new_purchase_price
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
    if keep_tier == "old":
        product.purchase_price = product.old_purchase_price
        product.sale_price = product.old_sale_price
    # else "new" — keep current prices as-is

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

