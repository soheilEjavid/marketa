import json
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    CheckStatus,
    Customer,
    CustomerPayment,
    DocumentStatus,
    InventoryTransaction,
    InventoryTransactionType,
    PaymentMethod,
    Product,
    Sale,
    SaleItem,
    SalePaymentLine,
)
from app.schemas.financial import PaymentCreate
from app.schemas.sale import SaleCreate, SaleEditRequest, SalePaymentLineInput
from app.services.financials import payment_status, record_customer_payment
from app.services.loyalty import REDEMPTION_CAP_PCT, LoyaltyError, award_points_for_payment, redeem_points
from app.services.products import decrement_old_stock_estimate
from app.services.shifts import get_open_shift


class SaleError(ValueError):
    pass


class ProductNotFoundError(SaleError):
    pass


class InsufficientStockError(SaleError):
    pass


class DuplicateInvoiceError(SaleError):
    pass


class CreditLimitExceededError(SaleError):
    """Raised when completing a sale would push a customer's balance past
    their credit_limit, and no valid admin/manager override was supplied."""

    def __init__(self, *, current_balance: Decimal, credit_limit: Decimal, credit_portion: Decimal) -> None:
        self.current_balance = current_balance
        self.credit_limit = credit_limit
        self.credit_portion = credit_portion
        super().__init__(
            f"This sale would exceed the customer's credit limit: current balance "
            f"{current_balance}, credit limit {credit_limit}, credit portion of this "
            f"sale {credit_portion}"
        )


def _invoice_number() -> str:
    date_part = datetime.now(UTC).strftime("%Y%m%d")
    return f"SAL-{date_part}-{uuid4().hex[:8].upper()}"


def _resolve_price_tier(
    product: Product,
    item_data,
) -> tuple[Decimal, Decimal, str | None]:
    """Resolve unit_price, cost_price, and price_tier for a sale item."""
    unit_price: Decimal
    cost_price: Decimal
    price_tier: str | None = None

    if product.is_dual_priced and getattr(item_data, "price_tier", None):
        price_tier = item_data.price_tier
        if item_data.price_tier == "old":
            cost_price = product.old_purchase_price or product.purchase_price
            unit_price = item_data.unit_price or product.old_sale_price or product.sale_price
        else:  # "new"
            cost_price = product.purchase_price
            unit_price = item_data.unit_price or product.sale_price
    elif product.is_dual_priced and not getattr(item_data, "price_tier", None):
        # No tier specified — default to old price (prefer selling old stock first)
        price_tier = "old"
        cost_price = product.old_purchase_price or product.purchase_price
        unit_price = item_data.unit_price or product.old_sale_price or product.sale_price
    else:
        cost_price = product.purchase_price
        unit_price = item_data.unit_price or product.sale_price

    return unit_price, cost_price, price_tier


def _build_sale_items(
    database: Session,
    sale: Sale,
    data: SaleCreate,
    products: dict[int, Product],
) -> Decimal:
    """Create SaleItem rows, adjust stock, and return subtotal."""
    subtotal = Decimal("0")
    for item_data in data.items:
        product = products[item_data.product_id]
        unit_price, cost_price, price_tier = _resolve_price_tier(product, item_data)

        line_total = unit_price * item_data.quantity - item_data.discount
        if line_total < 0:
            raise SaleError("Item discount cannot exceed its line value")

        database.add(
            SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                quantity=item_data.quantity,
                unit_price=unit_price,
                cost_price=cost_price,
                discount=item_data.discount,
                line_total=line_total,
                price_tier=price_tier,
            )
        )
        product.stock_quantity -= item_data.quantity

        # Decrement old-stock estimate if old tier selected
        if price_tier == "old":
            decrement_old_stock_estimate(database, product)

        database.add(
            InventoryTransaction(
                product_id=product.id,
                quantity_change=-item_data.quantity,
                transaction_type=InventoryTransactionType.SALE,
                related_id=sale.id,
            )
        )
        subtotal += line_total
    return subtotal


def _sale_item_snapshot(item: SaleItem) -> dict:
    return {
        "id": item.id,
        "product_id": item.product_id,
        "quantity": str(item.quantity),
        "unit_price": str(item.unit_price),
        "cost_price": str(item.cost_price),
        "discount": str(item.discount),
        "price_tier": item.price_tier,
    }


# Real tenders a SalePaymentLine can represent — "credit"/"loyalty"/"mixed"
# are display-only classifications on Sale.payment_method, never a line's
# own method (loyalty redemption is tracked separately via redeem_points()).
_REAL_TENDER_METHODS = {PaymentMethod.CASH, PaymentMethod.CARD, PaymentMethod.CHECK}


def _add_sale_payment_line(
    database: Session,
    sale: Sale,
    *,
    method: PaymentMethod | str,
    amount: Decimal,
    check_number: str | None = None,
    check_bank_name: str | None = None,
    check_due_date=None,
    notes: str | None = None,
) -> None:
    """Record one payment line for shift cash-reconciliation purposes (see
    services/shifts.py::close_shift). Mirrors purchases'
    _apply_payment_line, minus the party-balance update — a sale's
    customer-balance/loyalty effect is handled separately via
    record_customer_payment()/award_points_for_payment(), which this table
    intentionally does not duplicate.
    """
    resolved_method = PaymentMethod(method)
    database.add(
        SalePaymentLine(
            sale=sale,
            amount=amount,
            method=resolved_method,
            notes=notes,
            check_number=check_number,
            check_bank_name=check_bank_name,
            check_due_date=check_due_date,
            check_status=CheckStatus.PENDING if resolved_method == PaymentMethod.CHECK else None,
        )
    )


def process_sale(database: Session, data: SaleCreate, *, credit_override_authorized: bool = False) -> Sale:
    requested_quantities: dict[int, Decimal] = defaultdict(Decimal)
    for item in data.items:
        requested_quantities[item.product_id] += item.quantity

    try:
        products = {
            product.id: product
            for product in database.scalars(
                select(Product)
                .where(
                    Product.id.in_(requested_quantities),
                    Product.is_active.is_(True),
                )
                .with_for_update()
            )
        }
        missing_ids = set(requested_quantities) - set(products)
        if missing_ids:
            raise ProductNotFoundError(
                f"Products not found or inactive: {sorted(missing_ids)}"
            )

        for product_id, quantity in requested_quantities.items():
            product = products[product_id]
            if product.stock_quantity < quantity:
                raise InsufficientStockError(
                    f"Insufficient stock for {product.name}: "
                    f"requested {quantity}, available {product.stock_quantity}"
                )

        customer = database.get(Customer, data.customer_id) if data.customer_id else None
        if data.customer_id and (customer is None or not customer.is_active):
            raise SaleError("Customer not found or inactive")
        # Captured before award_points_for_payment()'s _ensure_membership()
        # can flip it, so the caller can tell whether *this* sale is what
        # crossed the membership threshold (see routes/sales.py).
        was_loyalty_member = customer.loyalty_member if customer else False
        # Captured before customer.balance += sale.total below, so the
        # credit-limit check can report the pre-sale balance in its error.
        balance_before_sale = customer.balance if customer else Decimal("0")

        open_shift = get_open_shift(database)

        sale = Sale(
            invoice_number=data.invoice_number or _invoice_number(),
            customer_id=data.customer_id,
            discount=data.discount,
            paid_amount=Decimal("0"),
            payment_method=data.payment_method,
            status=DocumentStatus.COMPLETED,
            notes=data.notes,
            shift_id=open_shift.id if open_shift else None,
        )
        database.add(sale)
        database.flush()

        subtotal = _build_sale_items(database, sale, data, products)

        sale.subtotal = subtotal
        sale.total = subtotal - data.discount
        if sale.total < 0:
            raise SaleError("Sale discount cannot exceed the subtotal")
        if data.redeem_points > 0 and not customer:
            raise SaleError("Cannot redeem loyalty points without a customer")

        sale.paid_amount = Decimal("0")
        sale.remaining_amount = sale.total
        sale.payment_status = payment_status(sale.total, Decimal("0"))

        # award_points_for_payment() reads sale.items via a lazy-loaded
        # relationship; this session has autoflush disabled, so the
        # PurchaseItem/SaleItem rows _build_sale_items() just added via
        # database.add() would otherwise be invisible to that query until
        # an explicit flush.
        database.flush()

        if customer:
            customer.balance += sale.total
            # Redeem BEFORE computing the default "paid now" amount, so a
            # cash/card sale that isn't given an explicit paid_amount
            # naturally only asks for whatever's left after points cover
            # their share — not the pre-redemption total.
            if data.redeem_points > 0:
                try:
                    redeem_points(database, customer, sale, data.redeem_points)
                except LoyaltyError as error:
                    raise SaleError(str(error)) from error

        if data.payment_lines:
            # New split-payment path: lines are validated against the
            # post-redemption remainder, then applied in submission order.
            lines_total = sum((line.amount for line in data.payment_lines), Decimal("0"))
            if lines_total > sale.remaining_amount:
                raise SaleError("Paid amount cannot exceed the remaining sale amount")
            for line in data.payment_lines:
                _add_sale_payment_line(
                    database,
                    sale,
                    method=line.method,
                    amount=line.amount,
                    check_number=line.check_number,
                    check_bank_name=line.check_bank_name,
                    check_due_date=line.check_due_date,
                    notes=line.notes,
                )
                if customer:
                    record_customer_payment(database, customer, PaymentCreate(amount=line.amount, document_id=sale.id, method=PaymentMethod(line.method), reference=f"{sale.invoice_number}-{line.method.upper()}"), commit=False)
                    award_points_for_payment(database, customer, sale, line.amount)
                else:
                    sale.paid_amount += line.amount
                    sale.remaining_amount = sale.total - sale.paid_amount
                    sale.payment_status = payment_status(sale.total, sale.paid_amount)
            sale.payment_method = (
                PaymentMethod(data.payment_lines[0].method)
                if len(data.payment_lines) == 1
                else PaymentMethod.MIXED
            )
        elif customer:
            # Legacy single-method path — unchanged behavior. Still backs
            # a SalePaymentLine for shift cash-reconciliation whenever a
            # real tender (not "credit"/"loyalty"/"mixed") was used.
            initial_paid = sale.remaining_amount if data.paid_amount is None else data.paid_amount
            if initial_paid > sale.remaining_amount:
                raise SaleError("Paid amount cannot exceed the remaining sale amount")
            if initial_paid > 0:
                record_customer_payment(database, customer, PaymentCreate(amount=initial_paid, document_id=sale.id, method=data.payment_method, reference=f"{sale.invoice_number}-INITIAL"), commit=False)
                award_points_for_payment(database, customer, sale, initial_paid)
                if data.payment_method in _REAL_TENDER_METHODS:
                    _add_sale_payment_line(database, sale, method=data.payment_method, amount=initial_paid)
        else:
            initial_paid = sale.total if data.paid_amount is None else data.paid_amount
            if initial_paid > sale.total:
                raise SaleError("Paid amount cannot exceed the sale total")
            sale.paid_amount = initial_paid
            sale.remaining_amount = sale.total - initial_paid
            sale.payment_status = payment_status(sale.total, initial_paid)
            if initial_paid > 0 and data.payment_method in _REAL_TENDER_METHODS:
                _add_sale_payment_line(database, sale, method=data.payment_method, amount=initial_paid)

        # Credit-limit enforcement — only sales that leave a real unpaid
        # portion on a customer's account can trip this; cash/card-only
        # sales (remaining_amount == 0) are never affected. customer.balance
        # here already equals balance_before_sale + sale.remaining_amount,
        # since every payment/redemption branch above has already reduced it
        # by whatever was actually tendered.
        if customer and sale.remaining_amount > 0:
            limit = customer.credit_limit
            if limit and limit > 0 and customer.balance > limit and not credit_override_authorized:
                raise CreditLimitExceededError(
                    current_balance=balance_before_sale,
                    credit_limit=limit,
                    credit_portion=sale.remaining_amount,
                )

        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise DuplicateInvoiceError("Invoice number is already in use") from error
    except Exception:
        database.rollback()
        raise

    result = database.scalar(
        select(Sale)
        .where(Sale.id == sale.id)
        .options(selectinload(Sale.items), selectinload(Sale.payment_lines))
    )
    # Transient, never persisted — read by SaleRead for the post-checkout
    # "customer just became a loyalty member" banner (see routes/sales.py).
    result.loyalty_membership_just_earned = bool(customer) and not was_loyalty_member and customer.loyalty_member
    return result


def hold_sale(database: Session, data: SaleCreate) -> Sale:
    """Persist the current POS cart as a DRAFT sale — no stock decrement, no
    InventoryTransaction rows, no customer-balance effect. Resuming happens
    by re-hydrating the cart in the frontend and re-submitting it through
    the normal process_sale() path as a brand-new sale; the draft row is
    then cancelled (see cancel_held_sale). This guarantees inventory is
    only ever decremented once, through the one already-tested code path,
    with no changes to process_sale/edit_sale themselves.
    """
    product_ids = {item.product_id for item in data.items}

    try:
        products = {
            product.id: product
            for product in database.scalars(
                select(Product).where(Product.id.in_(product_ids), Product.is_active.is_(True))
            )
        }
        missing_ids = product_ids - set(products)
        if missing_ids:
            raise ProductNotFoundError(f"Products not found or inactive: {sorted(missing_ids)}")

        customer = database.get(Customer, data.customer_id) if data.customer_id else None
        if data.customer_id and (customer is None or not customer.is_active):
            raise SaleError("Customer not found or inactive")

        open_shift = get_open_shift(database)

        sale = Sale(
            invoice_number=data.invoice_number or _invoice_number(),
            customer_id=data.customer_id,
            discount=data.discount,
            paid_amount=Decimal("0"),
            payment_method=data.payment_method,
            status=DocumentStatus.DRAFT,
            notes=data.notes,
            shift_id=open_shift.id if open_shift else None,
        )
        database.add(sale)
        database.flush()

        subtotal = Decimal("0")
        for item_data in data.items:
            product = products[item_data.product_id]
            unit_price, cost_price, price_tier = _resolve_price_tier(product, item_data)
            line_total = unit_price * item_data.quantity - item_data.discount
            if line_total < 0:
                raise SaleError("Item discount cannot exceed its line value")
            database.add(
                SaleItem(
                    sale_id=sale.id,
                    product_id=product.id,
                    quantity=item_data.quantity,
                    unit_price=unit_price,
                    cost_price=cost_price,
                    discount=item_data.discount,
                    line_total=line_total,
                    price_tier=price_tier,
                )
            )
            subtotal += line_total

        sale.subtotal = subtotal
        sale.total = subtotal - data.discount
        if sale.total < 0:
            raise SaleError("Sale discount cannot exceed the subtotal")
        sale.remaining_amount = sale.total
        sale.payment_status = payment_status(sale.total, Decimal("0"))

        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise DuplicateInvoiceError("Invoice number is already in use") from error
    except Exception:
        database.rollback()
        raise

    return database.scalar(
        select(Sale).where(Sale.id == sale.id).options(selectinload(Sale.items), selectinload(Sale.payment_lines))
    )


def list_held_sales(database: Session) -> list[Sale]:
    return list(
        database.scalars(
            select(Sale)
            .where(Sale.status == DocumentStatus.DRAFT)
            .options(selectinload(Sale.items), selectinload(Sale.payment_lines))
            .order_by(Sale.created_at.desc())
        )
    )


def cancel_held_sale(database: Session, sale: Sale) -> Sale:
    """Marks a held (DRAFT) sale CANCELLED — used both when the cashier
    discards it outright and when it's superseded by a freshly-completed
    sale on resume. Kept as a row (not deleted) so cashier-performance
    reporting can count holds/resumes/discards from the audit log; the
    route layer logs a different audit action per case since a resumed and
    an abandoned draft are otherwise indistinguishable by status alone.
    """
    if sale.status != DocumentStatus.DRAFT:
        raise SaleError("Only a held (draft) sale can be discarded or resumed")
    sale.status = DocumentStatus.CANCELLED
    database.commit()
    database.refresh(sale)
    return sale


def edit_sale(database: Session, sale: Sale, data: SaleEditRequest) -> tuple[Sale, str]:
    """Edit an existing sale's line items and/or invoice discount.

    Computes per-line stock/cost deltas rather than reversing and rebuilding
    the whole sale from current product state — see the module-level design
    notes in the invoice-editing task. Returns (updated_sale, audit_details)
    so the route can log the edit only after this commits successfully.
    """
    if sale.status == DocumentStatus.CANCELLED:
        raise SaleError("Cannot edit a cancelled sale")

    old_items_by_id: dict[int, SaleItem] = {item.id: item for item in sale.items}
    new_item_ids = {item.id for item in data.items if item.id is not None}

    unknown_ids = new_item_ids - set(old_items_by_id)
    if unknown_ids:
        raise SaleError(f"Line item(s) {sorted(unknown_ids)} do not belong to this sale")

    for item_data in data.items:
        if item_data.id is not None and old_items_by_id[item_data.id].product_id != item_data.product_id:
            raise SaleError(
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

        # ── Compute net stock delta per product, validate BEFORE mutating ──
        # Positive delta = stock increases (line removed / quantity reduced).
        # Negative delta = stock decreases (quantity increased / new line).
        stock_deltas: dict[int, Decimal] = defaultdict(Decimal)
        for item in removed_items:
            stock_deltas[item.product_id] += item.quantity
        for item_data in data.items:
            if item_data.id is not None:
                old_item = old_items_by_id[item_data.id]
                qty_delta = item_data.quantity - old_item.quantity
                stock_deltas[item_data.product_id] -= qty_delta
            else:
                stock_deltas[item_data.product_id] -= item_data.quantity

        for product_id, delta in stock_deltas.items():
            resulting = products[product_id].stock_quantity + delta
            if resulting < 0:
                raise InsufficientStockError(
                    f"Insufficient stock for {products[product_id].name}: "
                    f"this edit would result in {resulting}"
                )

        old_snapshot = {
            "total": str(sale.total),
            "discount": str(sale.discount),
            "items": [_sale_item_snapshot(item) for item in sale.items],
        }

        # ── Apply stock deltas as ADJUSTMENT transactions — never delete or
        # rewrite the original SALE-type transactions, so InventoryHistory
        # keeps showing the real original event at its real timestamp. ──
        for product_id, delta in stock_deltas.items():
            if delta == 0:
                continue
            products[product_id].stock_quantity += delta
            database.add(
                InventoryTransaction(
                    product_id=product_id,
                    quantity_change=delta,
                    transaction_type=InventoryTransactionType.ADJUSTMENT,
                    related_id=sale.id,
                )
            )

        for item in removed_items:
            database.delete(item)

        subtotal = Decimal("0")
        for item_data in data.items:
            product = products[item_data.product_id]
            if item_data.id is not None:
                line = old_items_by_id[item_data.id]
                tier_changed = item_data.price_tier != line.price_tier
                if tier_changed:
                    # An explicit tier correction — recompute price/cost for
                    # the newly-asserted tier.
                    unit_price, cost_price, price_tier = _resolve_price_tier(product, item_data)
                else:
                    # Preserve the originally recorded cost basis. unit_price
                    # may still be corrected independently (it's revenue, not
                    # cost) if the edit explicitly supplies a new one.
                    cost_price = line.cost_price
                    unit_price = item_data.unit_price if item_data.unit_price is not None else line.unit_price
                    price_tier = line.price_tier
                line_total = unit_price * item_data.quantity - item_data.discount
                if line_total < 0:
                    raise SaleError("Item discount cannot exceed its line value")
                line.quantity = item_data.quantity
                line.unit_price = unit_price
                line.cost_price = cost_price
                line.discount = item_data.discount
                line.price_tier = price_tier
                line.line_total = line_total
            else:
                # Brand-new line — no history to preserve, cost comes from
                # the product's current state (same as a fresh sale line).
                unit_price, cost_price, price_tier = _resolve_price_tier(product, item_data)
                line_total = unit_price * item_data.quantity - item_data.discount
                if line_total < 0:
                    raise SaleError("Item discount cannot exceed its line value")
                database.add(
                    SaleItem(
                        sale_id=sale.id,
                        product_id=product.id,
                        quantity=item_data.quantity,
                        unit_price=unit_price,
                        cost_price=cost_price,
                        discount=item_data.discount,
                        line_total=line_total,
                        price_tier=price_tier,
                    )
                )
            subtotal += line_total

        old_total = sale.total
        sale.subtotal = subtotal
        sale.discount = data.discount
        sale.total = subtotal - data.discount
        if sale.total < 0:
            raise SaleError("Sale discount cannot exceed the subtotal")

        # An edit that shrinks the total can retroactively push a
        # points-redemption payment made at creation time past the
        # program's redemption cap (see services/loyalty.py::redeem_points).
        # Points already spent can't be silently un-redeemed here, so block
        # the edit instead — the same stance InsufficientStockError takes
        # for stock deltas above.
        already_redeemed = database.scalar(
            select(func.coalesce(func.sum(CustomerPayment.amount), 0)).where(
                CustomerPayment.sale_id == sale.id,
                CustomerPayment.method == PaymentMethod.LOYALTY,
            )
        )
        if already_redeemed > sale.total * REDEMPTION_CAP_PCT:
            raise SaleError(
                "This edit would leave the loyalty-point redemption already applied to this "
                "sale above the redemption cap for the new total — increase the total or "
                "reverse the redemption first"
            )

        total_delta = sale.total - old_total
        # paid_amount is untouched by an edit (no payment was made or
        # unmade) — remaining_amount simply absorbs the total's change.
        sale.remaining_amount = sale.remaining_amount + total_delta
        sale.payment_status = payment_status(sale.total, sale.paid_amount)

        if sale.customer_id:
            customer = database.get(Customer, sale.customer_id)
            if customer:
                customer.balance += total_delta

        database.flush()
        new_snapshot = {
            "total": str(sale.total),
            "discount": str(sale.discount),
            "items": [_sale_item_snapshot(item) for item in sale.items],
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
        select(Sale).where(Sale.id == sale.id).options(selectinload(Sale.items), selectinload(Sale.payment_lines))
    )
    return updated, audit_details


def get_sale(database: Session, sale_id: int) -> Sale | None:
    return database.scalar(
        select(Sale)
        .where(Sale.id == sale_id)
        .options(selectinload(Sale.items), selectinload(Sale.payment_lines))
    )

def list_sales(
    database: Session,
    *,
    search: str | None = None,
    sort: str = "date_desc",
    offset: int = 0,
    limit: int = 100,
) -> list[Sale]:
    # Held (DRAFT) and cancelled sales are deliberately excluded — they
    # aren't real, finalized transactions and shouldn't appear in history.
    query = select(Sale).where(Sale.status == DocumentStatus.COMPLETED).options(selectinload(Sale.items), selectinload(Sale.payment_lines))
    if search:
        pattern = f"%{search.strip()}%"
        query = query.outerjoin(Customer, Sale.customer_id == Customer.id).where(
            or_(Sale.invoice_number.ilike(pattern), Customer.full_name.ilike(pattern))
        )
    query = query.order_by(Sale.created_at.asc() if sort == "date_asc" else Sale.created_at.desc())
    return list(database.scalars(query.offset(offset).limit(limit)))


def count_sales(database: Session, *, search: str | None = None) -> int:
    from sqlalchemy import func

    query = select(func.count(Sale.id)).select_from(Sale).where(Sale.status == DocumentStatus.COMPLETED)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.outerjoin(Customer, Sale.customer_id == Customer.id).where(
            or_(Sale.invoice_number.ilike(pattern), Customer.full_name.ilike(pattern))
        )
    return database.scalar(query) or 0