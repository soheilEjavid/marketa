from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UtcDateTime


class PaymentMethod(StrEnum):
    CASH = "cash"
    CARD = "card"
    # کارت به کارت — the customer transfers straight to the shop owner's card
    # from their phone; no POS terminal is involved. Tracked separately from
    # CARD on purpose: it is an anti-theft control, not a cosmetic label. An
    # employee can tell a customer to transfer to *their own* card number and
    # the sale still looks paid, so the owner needs a per-shift total to
    # reconcile against what actually landed in their bank account. It never
    # enters the till, so close_shift() must keep excluding it from expected
    # cash (it already does — that query filters on CASH).
    CARD_TO_CARD = "card_to_card"
    CREDIT = "credit"
    MIXED = "mixed"
    CHECK = "check"
    # A CustomerPayment made by redeeming loyalty points rather than real
    # money — see services/loyalty.py. Never used for Sale.payment_method
    # or purchase-side payment lines, only CustomerPayment.method.
    LOYALTY = "loyalty"


class DocumentStatus(StrEnum):
    DRAFT = "draft"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PaymentStatus(StrEnum):
    PAID = "paid"
    PARTIAL = "partial"
    UNPAID = "unpaid"


class ShiftStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class CheckStatus(StrEnum):
    """Manually-tracked status for چک (check) payment lines — there is no
    bank integration, so this is only ever changed by a user action."""

    PENDING = "pending"
    CLEARED = "cleared"
    BOUNCED = "bounced"


class InventoryTransactionType(StrEnum):
    PURCHASE = "purchase"
    SALE = "sale"
    ADJUSTMENT = "adjustment"


class LoyaltyTransactionType(StrEnum):
    """See services/loyalty.py for the full earning/redemption/expiry rules."""

    EARN = "earn"
    REDEEM = "redeem"
    EXPIRE = "expire"
    ADJUST = "adjust"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(30), default="cashier")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Category(Base, TimestampMixin):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)

    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    barcode: Mapped[str | None] = mapped_column(String(80), unique=True, index=True)
    sku: Mapped[str | None] = mapped_column(String(60), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    brand: Mapped[str | None] = mapped_column(String(100))
    purchase_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    sale_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    min_sale_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    stock_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    low_stock_threshold: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    # Sold by weight rather than by the piece: the POS asks for a decimal
    # weight instead of stepping a whole-unit counter, and every quantity
    # for this product is displayed to three decimals. `unit` (below) is
    # the label that weight is shown in — کیلوگرم, گرم — and stays a plain
    # free-text field, because it was already one and shops have already
    # filled it in. This flag is the behaviour; `unit` is the wording.
    #
    # Prices are unchanged in meaning: sale_price/purchase_price are per
    # one `unit`, exactly as they are for a counted product.
    is_weighted: Mapped[bool] = mapped_column(Boolean, default=False)
    unit: Mapped[str | None] = mapped_column(String(30))
    packaging_unit_label: Mapped[str | None] = mapped_column(String(40))
    packaging_unit_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    image_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    expiration_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    # Manager override of the automatic margin/dead-stock loyalty earn rate
    # (see services/loyalty.py::_line_multiplier) — null means "let the
    # automatic calculation decide"; 0 exempts this product from earning
    # points entirely; any other value replaces the computed multiplier
    # outright (the dead-stock boost is NOT layered on top of an override —
    # a manual figure is the manager's final word).
    loyalty_point_multiplier: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))

    # ── Dual-price fields ────────────────────────────────────────────────
    is_dual_priced: Mapped[bool] = mapped_column(Boolean, default=False)
    old_purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    old_sale_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    # Numeric, not Integer: a weighted product's old stock is 4.500 kg, and
    # this is decremented by the quantity actually sold (see
    # services/products.py::decrement_old_stock_estimate).
    old_price_stock_estimate: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    dual_price_started_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    category: Mapped[Category | None] = relationship(back_populates="products")
    sale_items: Mapped[list["SaleItem"]] = relationship(back_populates="product")
    purchase_items: Mapped[list["PurchaseItem"]] = relationship(back_populates="product")
    inventory_transactions: Mapped[list["InventoryTransaction"]] = relationship(
        back_populates="product"
    )


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(160), index=True)
    phone: Mapped[str | None] = mapped_column(String(40), index=True)
    national_id: Mapped[str | None] = mapped_column(
        String(20), unique=True, index=True
    )
    address: Mapped[str | None] = mapped_column(Text)
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    birth_date: Mapped[date | None] = mapped_column(Date)
    # ── Loyalty program (باشگاه مشتریان) — see services/loyalty.py ────────
    # Cached/denormalized current balance, kept in sync by loyalty.py the
    # same way Product.stock_quantity is kept in sync by inventory writes —
    # loyalty_point_transactions remains the append-only source of truth.
    loyalty_points_balance: Mapped[int] = mapped_column(Integer, default=0)
    # Toman progress not yet converted into a whole point (avoids losing
    # fractional value across several small partial payments).
    loyalty_progress_toman: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    # Gate for the manager-configurable auto-enrollment threshold (see
    # services/loyalty.py). Pre-existing customers are grandfathered to
    # True by the migration that adds this column, since the original
    # design had everyone earning points already; new customers start
    # False and flip to True the moment a sale qualifies under
    # LoyaltySettings — or immediately, if no threshold is configured.
    loyalty_member: Mapped[bool] = mapped_column(Boolean, default=False)

    sales: Mapped[list["Sale"]] = relationship(back_populates="customer")
    payments: Mapped[list["CustomerPayment"]] = relationship(back_populates="customer")
    loyalty_transactions: Mapped[list["LoyaltyPointTransaction"]] = relationship(
        back_populates="customer", order_by="LoyaltyPointTransaction.created_at"
    )


class Supplier(Base, TimestampMixin):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    contact_person: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(40))
    address: Mapped[str | None] = mapped_column(Text)
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    last_purchase_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    purchases: Mapped[list["Purchase"]] = relationship(back_populates="supplier")
    payments: Mapped[list["SupplierPayment"]] = relationship(back_populates="supplier")


class Sale(Base, TimestampMixin):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    discount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    remaining_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    payment_status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus), default=PaymentStatus.UNPAID
    )
    payment_method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod), default=PaymentMethod.CASH
    )
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus), default=DocumentStatus.DRAFT
    )
    notes: Mapped[str | None] = mapped_column(Text)
    # Auto-attached to whichever CashierShift is OPEN at creation time (see
    # services/sales.py) — null if no shift was open, e.g. before this
    # feature existed or if the cashier forgot to open one.
    shift_id: Mapped[int | None] = mapped_column(ForeignKey("cashier_shifts.id"), index=True)

    customer: Mapped[Customer | None] = relationship(back_populates="sales")
    items: Mapped[list["SaleItem"]] = relationship(
        back_populates="sale", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="sale", cascade="all, delete-orphan"
    )
    customer_payments: Mapped[list["CustomerPayment"]] = relationship(back_populates="sale")
    payment_lines: Mapped[list["SalePaymentLine"]] = relationship(
        back_populates="sale", order_by="SalePaymentLine.paid_at, SalePaymentLine.id"
    )
    shift: Mapped["CashierShift | None"] = relationship(back_populates="sales")


class SaleItem(Base):
    __tablename__ = "sale_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    cost_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    discount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    price_tier: Mapped[str | None] = mapped_column(String(10))

    sale: Mapped[Sale] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(back_populates="sale_items")


class Purchase(Base, TimestampMixin):
    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    remaining_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    payment_status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus), default=PaymentStatus.UNPAID
    )
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus), default=DocumentStatus.DRAFT
    )
    notes: Mapped[str | None] = mapped_column(Text)

    supplier: Mapped[Supplier | None] = relationship(back_populates="purchases")
    items: Mapped[list["PurchaseItem"]] = relationship(
        back_populates="purchase", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="purchase", cascade="all, delete-orphan"
    )
    payment_lines: Mapped[list["SupplierPayment"]] = relationship(
        back_populates="purchase", order_by="SupplierPayment.paid_at, SupplierPayment.id"
    )


class PurchaseItem(Base):
    __tablename__ = "purchase_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(ForeignKey("purchases.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    selling_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    expiry_date: Mapped[date | None] = mapped_column(Date)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    purchase: Mapped[Purchase] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(back_populates="purchase_items")


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod))
    reference: Mapped[str | None] = mapped_column(String(120))
    sale_id: Mapped[int | None] = mapped_column(ForeignKey("sales.id"))
    purchase_id: Mapped[int | None] = mapped_column(ForeignKey("purchases.id"))

    sale: Mapped[Sale | None] = relationship(back_populates="payments")
    purchase: Mapped[Purchase | None] = relationship(back_populates="payments")


class CustomerPayment(Base, TimestampMixin):
    __tablename__ = "customer_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    sale_id: Mapped[int | None] = mapped_column(ForeignKey("sales.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod))
    reference: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    paid_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now(), index=True)

    customer: Mapped[Customer] = relationship(back_populates="payments")
    sale: Mapped[Sale | None] = relationship(back_populates="customer_payments")


class SupplierPayment(Base, TimestampMixin):
    __tablename__ = "supplier_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nullable: a purchase may have no supplier on file (walk-in purchase),
    # in which case its payment lines still need to be recorded, just with
    # no party ledger to post against.
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), index=True)
    purchase_id: Mapped[int | None] = mapped_column(ForeignKey("purchases.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod))
    reference: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    # ── چک (check) details — only populated when method == CHECK ──────────
    check_number: Mapped[str | None] = mapped_column(String(60))
    check_bank_name: Mapped[str | None] = mapped_column(String(120))
    check_due_date: Mapped[date | None] = mapped_column(Date, index=True)
    # Only meaningful when method == CHECK; null for cash/card lines.
    check_status: Mapped[CheckStatus | None] = mapped_column(Enum(CheckStatus))
    paid_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now(), index=True)

    supplier: Mapped[Supplier | None] = relationship(back_populates="payments")
    purchase: Mapped[Purchase | None] = relationship(back_populates="payment_lines")


class SalePaymentLine(Base, TimestampMixin):
    """One cash/card/check payment line against a sale — mirrors
    SupplierPayment's role on the purchase side. Unlike SupplierPayment,
    `sale_id` is never null: there's no "standalone sale payment" concept
    equivalent to a supplier balance settlement (that's CustomerPayment with
    sale_id=None, unchanged by this table).

    For a customer-linked sale, the same money is also recorded as a
    CustomerPayment (drives customer.balance + loyalty earning) — this
    table exists purely for the cash/card/check breakdown used by shift
    cash reconciliation (see services/shifts.py::close_shift) and by
    reports.payment_method_breakdown()/cashier_performance(), so a
    customer sale's paid amount is intentionally tracked in both places,
    each for its own job. This is NOT a bug to "deduplicate" later — never
    sum CustomerPayment and SalePaymentLine together for the same sale, that
    would double-count the money; each table must only ever be totalled on
    its own.
    """

    __tablename__ = "sale_payment_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod))
    reference: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    # ── چک (check) details — only populated when method == CHECK ──────────
    check_number: Mapped[str | None] = mapped_column(String(60))
    check_bank_name: Mapped[str | None] = mapped_column(String(120))
    check_due_date: Mapped[date | None] = mapped_column(Date, index=True)
    check_status: Mapped[CheckStatus | None] = mapped_column(Enum(CheckStatus))
    paid_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now(), index=True)

    sale: Mapped["Sale"] = relationship(back_populates="payment_lines")


class CashierShift(Base, TimestampMixin):
    """A till session: opened by picking a cashier + starting cash float,
    closed with a counted-cash reconciliation. `cashier_id` here records who
    is working the register.

    **Only one shift may be OPEN at a time**, and that is now a database
    constraint rather than only a Python check. services/shifts.py still
    checks first so the user gets a clean error instead of an IntegrityError,
    but the check-then-insert there is not atomic and cannot be made so in
    application code. The rule matters more than most: close_shift() relies
    on it to justify having no upper time bound on its cash-out queries, and
    those queries filter on nothing but a timestamp — so two overlapping open
    shifts would deduct the same cash expense from both of them.

    The predicate matches 'OPEN', not 'open': SQLAlchemy's Enum persists the
    member *name*, and an index predicate written against the lowercase value
    would match no row ever and quietly enforce nothing.
    """

    __tablename__ = "cashier_shifts"
    __table_args__ = (
        Index(
            "uq_cashier_shifts_single_open",
            "status",
            unique=True,
            sqlite_where=text("status = 'OPEN'"),
            postgresql_where=text("status = 'OPEN'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cashier_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[ShiftStatus] = mapped_column(Enum(ShiftStatus), default=ShiftStatus.OPEN, index=True)
    opening_cash: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    closing_cash: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    expected_cash: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    difference: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    opened_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now(), index=True)
    closed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    notes: Mapped[str | None] = mapped_column(Text)

    cashier: Mapped["User"] = relationship()
    sales: Mapped[list["Sale"]] = relationship(back_populates="shift")


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    username: Mapped[str | None] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(50), index=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int | None] = mapped_column(Integer, index=True)
    details: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), index=True
    )


class InventoryTransaction(Base):
    __tablename__ = "inventory_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    quantity_change: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    transaction_type: Mapped[InventoryTransactionType] = mapped_column(
        Enum(InventoryTransactionType)
    )
    related_id: Mapped[int | None] = mapped_column(Integer, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        UtcDateTime, server_default=func.now(), index=True
    )

    product: Mapped[Product] = relationship(back_populates="inventory_transactions")


class LoyaltyPointTransaction(Base, TimestampMixin):
    """Append-only ledger for the loyalty points program — see
    services/loyalty.py. `points` is signed: positive for EARN/ADJUST-up,
    negative for REDEEM/EXPIRE/ADJUST-down. `expires_at` is only set on
    EARN rows (used by the lazy expiry sweep); `sale_id` links an
    EARN/REDEEM row to the sale that generated it, when there is one.
    """

    __tablename__ = "loyalty_point_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    points: Mapped[int] = mapped_column(Integer)
    transaction_type: Mapped[LoyaltyTransactionType] = mapped_column(Enum(LoyaltyTransactionType))
    sale_id: Mapped[int | None] = mapped_column(ForeignKey("sales.id"), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime, index=True)
    expired: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer)

    customer: Mapped[Customer] = relationship(back_populates="loyalty_transactions")


class LoyaltySettings(Base, TimestampMixin):
    """Single-row (id=1) manager-tunable loyalty configuration — everything
    that shouldn't require a code change/redeploy to adjust, unlike the
    constants in services/loyalty.py. NULL thresholds mean "disabled":
    every customer is an automatic member from their very first
    points-earning sale, matching the program's original design.
    """

    __tablename__ = "loyalty_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    min_invoice_total_for_membership: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    min_invoice_profit_for_membership: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    # Spend thresholds for the silver/gold customer tiers (see
    # services/loyalty.py::customer_tier) — null disables that tier.
    # Bronze is the implicit base tier and needs no threshold.
    tier_silver_min_spend: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    tier_gold_min_spend: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    # How far back tier spend is measured, in days. Null (the default)
    # keeps the original all-time/lifetime behavior; a manager can set e.g.
    # 180 so a customer who bought a lot two years ago but hasn't been back
    # since isn't still classified gold today.
    tier_window_days: Mapped[int | None] = mapped_column(Integer)
    # Multiplicative bonus applied on top of a sale's whole computed earn
    # value for silver/gold-tier customers (e.g. 1.1 = +10%) — see
    # services/loyalty.py::_tier_earn_bonus. Null = no bonus (1x). Bronze
    # never gets a bonus; it's the base tier.
    tier_silver_earn_bonus: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    tier_gold_earn_bonus: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    # Bonus points auto-granted to a churn-risk customer when a
    # manager triggers issue_churn_recovery_coupons() — null/0 disables
    # the feature (see services/loyalty.py).
    churn_recovery_coupon_points: Mapped[int | None] = mapped_column(Integer)
    updated_by_user_id: Mapped[int | None] = mapped_column(Integer)


class ExpensePaymentMethod(StrEnum):
    """Deliberately just cash/bank — distinct from PaymentMethod (sales/
    purchases), whose CARD/CREDIT/CHECK/LOYALTY values describe a
    customer-facing tender, not how the store itself paid out an operating
    expense or a salary. See docs/expense-management.md."""

    CASH = "cash"
    BANK = "bank"


class Expense(Base, TimestampMixin):
    """A general/fixed operating expense (rent, utilities, insurance,
    repairs, ads, etc.) — see docs/expense-management.md. `category` is a
    plain free-text column, not a foreign key to `Category`: that table is
    product-specific (globally-unique `name`, back-populated only from
    `Product`), and reusing it here would let an expense category collide
    with a product category of the same name. A `<datalist>` of distinct
    existing values on the frontend gives the same "manageable, not a
    locked enum" feel without that coupling.
    """

    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(100), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    date: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    payment_method: Mapped[ExpensePaymentMethod] = mapped_column(Enum(ExpensePaymentMethod))
    receipt_image_url: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer)


class SalaryPayment(Base, TimestampMixin):
    """One real, explicit payroll payment for one employee for one month —
    never auto-generated (see docs/expense-management.md's "ماهانه و
    تکرارشونده، ولی هر پرداخت واقعی جداگانه ثبت می‌شود"). `net_amount` is
    always computed by services/expenses.py as
    base_amount + bonus_amount - deductions_amount — never a free-standing
    user input, matching how Sale.total/Purchase.total are always derived
    from their line items rather than typed separately.

    The (employee_id, period_year, period_month) unique constraint is a
    deliberate safety addition beyond the doc's literal spec: this is
    payroll money — silently allowing two payment rows for the same
    employee/month would double-count in net_profit() and in the
    employee's own pay history with no natural way to notice.
    """

    __tablename__ = "salary_payments"
    __table_args__ = (
        UniqueConstraint("employee_id", "period_year", "period_month", name="uq_salary_payments_employee_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    period_month: Mapped[int] = mapped_column(Integer)
    period_year: Mapped[int] = mapped_column(Integer)
    base_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    bonus_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    deductions_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    payment_method: Mapped[ExpensePaymentMethod] = mapped_column(Enum(ExpensePaymentMethod))
    paid_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer)

    employee: Mapped["User"] = relationship()
    advances: Mapped[list["SalaryAdvance"]] = relationship(back_populates="settled_in_payment")


class SalaryAdvance(Base, TimestampMixin):
    """A مساعده (mid-month advance) against an employee's salary — its own
    record (not a free-typed number in SalaryPayment.deductions_amount) so
    there's a real history of *why* a deduction happened. `settled_in_payment_id`
    is null until services/expenses.py folds it into a specific month's
    SalaryPayment.deductions_amount — see docs/expense-management.md.
    """

    __tablename__ = "salary_advances"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    date: Mapped[date] = mapped_column(Date, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    settled_in_payment_id: Mapped[int | None] = mapped_column(ForeignKey("salary_payments.id"), index=True)

    employee: Mapped["User"] = relationship()
    settled_in_payment: Mapped["SalaryPayment | None"] = relationship(back_populates="advances")

