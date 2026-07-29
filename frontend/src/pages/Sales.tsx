import { useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  History,
  Layers,
  Minus,
  PauseCircle,
  Plus,
  Search,
  ShoppingCart,
  Tag,
  Trash2,
  Wallet,
  X,
} from "lucide-react";

import {
  ApiError,
  createSale,
  discardSale,
  getCustomers,
  getHeldSales,
  getLoyaltyBalance,
  getLoyaltySettings,
  getProducts,
  holdSale,
  resumeSale,
} from "../api";
import { useI18n } from "../i18n";
import { canOverrideCreditLimit } from "../permissions";
import { getSession } from "../session";
import type { Customer, LoyaltyBalance, Product, Sale, SalePaymentMethod } from "../types";
import { CashierShiftBar } from "../components/CashierShiftBar";
import { CustomerCombobox } from "../components/CustomerCombobox";
import { HeldSalesTab } from "../components/HeldSalesTab";
import { JalaliDatePicker } from "../components/JalaliDatePicker";
import { Modal } from "../components/Modal";
import { PostCheckoutLoyaltyPrompt, type PostCheckoutLoyaltyPrompt as PostCheckoutLoyaltyPromptType } from "../components/PostCheckoutLoyaltyPrompt";
import { QuickAddLoyaltyCustomerButton } from "../components/QuickAddLoyaltyCustomerButton";
import { ReceiptView, type ReceiptData } from "../components/ReceiptView";
import { SalesHistoryTab } from "../components/SalesHistoryTab";
import { SaleDetailView } from "../components/SaleDetailView";
import { getStockStatus } from "../lib/stockStatus";

type PaymentLine = {
  key: number;
  method: SalePaymentMethod;
  amount: number;
  checkNumber: string;
  checkBankName: string;
  checkDueDate: string;
  notes: string;
};

let nextPaymentLineKey = 1;

type CartLine = {
  product: Product;
  quantity: number;
  /** Which price tier was picked for a dual-priced product. */
  priceTier?: "old" | "new";
  /** Flat amount discount for this line. */
  discount?: number;
};

/** Effective unit price for a cart line, honoring the selected price tier. */
function lineUnitPrice(line: CartLine): number {
  if (line.product.is_dual_priced && line.priceTier === "old") {
    return Number(line.product.old_sale_price ?? line.product.sale_price);
  }
  return Number(line.product.sale_price);
}

export function Sales() {
  const { money, number, t } = useI18n();
  const [products, setProducts] = useState<Product[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [cart, setCart] = useState<CartLine[]>([]);
  const [query, setQuery] = useState("");
  const [paymentLines, setPaymentLines] = useState<PaymentLine[]>([]);
  const [customerId, setCustomerId] = useState<number | null>(null);
  const [loyaltyBalance, setLoyaltyBalance] = useState<LoyaltyBalance | null>(null);
  const [redeemPoints, setRedeemPoints] = useState("");
  const [invoiceDiscount, setInvoiceDiscount] = useState("");
  const [status, setStatus] = useState<"idle" | "submitting" | "success" | "error">("idle");
  const [message, setMessage] = useState("");
  const [receipt, setReceipt] = useState<ReceiptData | null>(null);
  const [tab, setTab] = useState<"checkout" | "held" | "history">("checkout");
  const [viewingSaleId, setViewingSaleId] = useState<number | null>(null);
  /** Product ids whose per-line discount input is currently expanded —
   * purely a UI reveal state, most lines never need this open. */
  const [expandedDiscounts, setExpandedDiscounts] = useState<Set<number>>(new Set());
  const [heldSales, setHeldSales] = useState<Sale[]>([]);
  /** Which held invoice (if any) the current cart's contents came from —
   * drives the "active tab" highlight, like a browser tab strip. */
  const [activeHeldSaleId, setActiveHeldSaleId] = useState<number | null>(null);
  /** LoyaltySettings.min_invoice_total_for_membership — fetched once, used
   * only to decide whether to show the post-checkout "register this
   * customer for the loyalty club" suggestion (Case 2, no customer
   * attached). Null/unset means the feature is off, matching the existing
   * convention elsewhere in the loyalty program. */
  const [minInvoiceTotalForMembership, setMinInvoiceTotalForMembership] = useState<number | null>(null);
  const [loyaltyPrompt, setLoyaltyPrompt] = useState<PostCheckoutLoyaltyPromptType | null>(null);
  const [creditLimitError, setCreditLimitError] = useState<ApiError["creditInfo"] | null>(null);
  const canOverride = canOverrideCreditLimit(getSession()?.role ?? "");

  useEffect(() => {
    Promise.all([getProducts(), getCustomers()])
      .then(([productsData, customersData]) => {
        setProducts(productsData);
        setCustomers(customersData);
      })
      .catch(() => {
        setStatus("error");
        setMessage(t("apiError"));
      });
    getLoyaltySettings()
      .then((settings) => {
        setMinInvoiceTotalForMembership(
          settings.min_invoice_total_for_membership != null ? Number(settings.min_invoice_total_for_membership) : null,
        );
      })
      .catch(() => {});
  }, [t]);

  function loadHeldSales() {
    getHeldSales()
      .then(setHeldSales)
      .catch(() => {});
  }

  useEffect(() => {
    if (tab === "checkout") loadHeldSales();
  }, [tab]);

  const filteredProducts = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return products.filter(
      (product) =>
        !normalized ||
        product.name.toLowerCase().includes(normalized) ||
        product.barcode?.toLowerCase().includes(normalized),
    );
  }, [products, query]);

  const itemDiscountsTotal = cart.reduce((sum, line) => sum + (line.discount || 0), 0);
  const subtotalBeforeDiscount = cart.reduce(
    (sum, line) => sum + lineUnitPrice(line) * line.quantity,
    0,
  );
  const invoiceDiscountValue = Number(invoiceDiscount) || 0;
  const total = Math.max(0, subtotalBeforeDiscount - itemDiscountsTotal - invoiceDiscountValue);

  // Client-side pre-check only — the backend validates payment lines
  // against the real post-redemption remaining amount. Redemption only
  // ever reduces what's owed further, so "lines exceed the pre-redemption
  // total" is always a safe rejection regardless of any points applied.
  const paidTotal = useMemo(
    () => paymentLines.reduce((sum, line) => sum + (Number(line.amount) || 0), 0),
    [paymentLines],
  );
  const remainingAfterPayment = Math.max(0, total - paidTotal);
  const paymentExceedsTotal = paidTotal > total;
  const hasIncompleteCheckLine = paymentLines.some(
    (line) => line.method === "check" && (!line.checkDueDate || !line.checkNumber.trim()),
  );

  // Loyalty balance for the selected customer, re-fetched whenever the
  // customer or the cart total changes (the redemption cap depends on it).
  useEffect(() => {
    if (!customerId || total <= 0) {
      setLoyaltyBalance(null);
      setRedeemPoints("");
      return;
    }
    let cancelled = false;
    getLoyaltyBalance(customerId, total)
      .then((balance) => {
        if (!cancelled) setLoyaltyBalance(balance);
      })
      .catch(() => {
        if (!cancelled) setLoyaltyBalance(null);
      });
    return () => {
      cancelled = true;
    };
  }, [customerId, total]);

  function parseNumeric(value: string): number {
    const parsed = Number(value);
    return Number.isNaN(parsed) ? 0 : parsed;
  }

  function addPaymentLine() {
    setPaymentLines((current) => [
      ...current,
      { key: nextPaymentLineKey++, method: "cash", amount: 0, checkNumber: "", checkBankName: "", checkDueDate: "", notes: "" },
    ]);
  }

  function updatePaymentLine(key: number, changes: Partial<PaymentLine>) {
    setPaymentLines((current) => current.map((line) => (line.key === key ? { ...line, ...changes } : line)));
  }

  function removePaymentLine(key: number) {
    setPaymentLines((current) => current.filter((line) => line.key !== key));
  }

  function addProduct(product: Product) {
    setStatus("idle");
    setCart((current) => {
      const existing = current.find((line) => line.product.id === product.id);
      if (existing) {
        if (existing.quantity >= Number(product.stock_quantity)) {
          setStatus("error");
          setMessage(t("insufficientStock"));
          return current;
        }
        return current.map((line) =>
          line.product.id === product.id
            ? { ...line, quantity: line.quantity + 1 }
            : line,
        );
      }
      if (Number(product.stock_quantity) <= 0) {
        setStatus("error");
        setMessage(t("insufficientStock"));
        return current;
      }
      return [
        ...current,
        // Default a dual-priced product to the old tier — old stock is
        // usually shelved first and should be sold through first.
        { product, quantity: 1, priceTier: product.is_dual_priced ? "old" : undefined },
      ];
    });
  }

  function setPriceTier(productId: number, tier: "old" | "new") {
    setCart((current) =>
      current.map((line) =>
        line.product.id === productId ? { ...line, priceTier: tier } : line,
      ),
    );
  }

  function updateItemDiscount(productId: number, value: string) {
    const parsed = Number(value);
    setCart((current) =>
      current.map((line) =>
        line.product.id === productId
          ? { ...line, discount: Number.isNaN(parsed) ? 0 : Math.max(0, parsed) }
          : line,
      ),
    );
  }

  function toggleDiscountInput(productId: number) {
    setExpandedDiscounts((current) => {
      const next = new Set(current);
      if (next.has(productId)) {
        next.delete(productId);
      } else {
        next.add(productId);
      }
      return next;
    });
  }

  function updateQuantity(productId: number, change: number) {
    setCart((current) =>
      current
        .map((line) => {
          if (line.product.id !== productId) return line;
          const quantity = Math.min(
            line.quantity + change,
            Number(line.product.stock_quantity),
          );
          return { ...line, quantity };
        })
        .filter((line) => line.quantity > 0),
    );
  }

  async function checkout(options?: { creditOverride?: boolean }) {
    if (!cart.length) return;
    if (remainingAfterPayment > 0 && !customerId) {
      setStatus("error");
      setMessage(t("customerRequiredForCredit"));
      return;
    }
    if (paymentExceedsTotal || hasIncompleteCheckLine) return;
    setStatus("submitting");
    setMessage("");
    setCreditLimitError(null);
    try {
      const activePaymentLines = paymentLines.filter((line) => line.amount > 0);
      const sale = await createSale({
        ...(customerId ? { customer_id: customerId } : {}),
        discount: invoiceDiscountValue,
        items: cart.map((line) => ({
          product_id: line.product.id,
          quantity: line.quantity,
          discount: line.discount || 0,
          ...(line.product.is_dual_priced && line.priceTier
            ? { price_tier: line.priceTier }
            : {}),
        })),
        ...(redeemPoints.trim() && Number(redeemPoints) > 0
          ? { redeem_points: Number(redeemPoints) }
          : {}),
        payment_lines: activePaymentLines.map((line) => ({
          method: line.method,
          amount: line.amount,
          ...(line.method === "check"
            ? {
                check_number: line.checkNumber.trim() || null,
                check_bank_name: line.checkBankName.trim() || null,
                check_due_date: line.checkDueDate || null,
              }
            : {}),
          ...(line.notes.trim() ? { notes: line.notes.trim() } : {}),
        })),
        // Zero payment lines means "nothing tendered now" — tell the
        // backend explicitly so it doesn't fall back to its legacy
        // default (cash, for the whole amount) for this new-style request.
        ...(activePaymentLines.length === 0 ? { payment_method: "credit" as const, paid_amount: 0 } : {}),
        ...(options?.creditOverride ? { allow_credit_override: true } : {}),
      });

      const customerName = customerId
        ? customers.find((c) => c.id === customerId)?.full_name ?? null
        : null;

      if (sale.loyalty_membership_just_earned && customerName) {
        setLoyaltyPrompt({ type: "celebrate", customerName });
      } else if (
        !sale.customer_id &&
        minInvoiceTotalForMembership !== null &&
        Number(sale.total) >= minInvoiceTotalForMembership
      ) {
        setLoyaltyPrompt({ type: "suggest", saleTotal: Number(sale.total) });
      } else {
        setLoyaltyPrompt(null);
      }

      setReceipt({
        invoiceNumber: sale.invoice_number,
        createdAt: sale.created_at,
        paymentMethod: sale.payment_method,
        customerName,
        lines: cart.map((line) => ({
          productName: line.product.name,
          quantity: line.quantity,
          unitPrice: lineUnitPrice(line),
          discount: line.discount || 0,
          lineTotal: lineUnitPrice(line) * line.quantity - (line.discount || 0),
          priceTier: line.product.is_dual_priced ? line.priceTier : undefined,
        })),
        // Pre-discount subtotal — sale.subtotal from the API already has
        // per-item discounts subtracted, which would double-count against
        // the combined discount line shown below.
        subtotal: subtotalBeforeDiscount,
        invoiceDiscount: invoiceDiscountValue,
        total: Number(sale.total),
        paidAmount: Number(sale.paid_amount),
        remainingAmount: Number(sale.remaining_amount),
      });

      setStatus("success");
      setMessage("");
      setCart([]);
      const hadCustomer = customerId !== null;
      setCustomerId(null);
      setPaymentLines([]);
      setInvoiceDiscount("");
      setRedeemPoints("");
      setLoyaltyBalance(null);
      setActiveHeldSaleId(null);
      setProducts(await getProducts());
      if (hadCustomer) {
        getCustomers().then(setCustomers).catch(() => {});
      }
    } catch (error) {
      if (error instanceof ApiError && error.code === "credit_limit_exceeded" && error.creditInfo) {
        setStatus("idle");
        setMessage("");
        setCreditLimitError(error.creditInfo);
        return;
      }
      setStatus("error");
      setMessage(error instanceof Error ? error.message : t("apiError"));
    }
  }

  /** Builds the SaleCreate payload for the current cart — shared by the
   * manual "تعلیق فاکتور" button and the tab strip's auto-hold-on-switch.
   * Payment isn't decided yet for a held sale (hold_sale() ignores it
   * entirely), so this deliberately omits payment_method/payment_lines. */
  function currentCartPayload() {
    return {
      ...(customerId ? { customer_id: customerId } : {}),
      discount: invoiceDiscountValue,
      items: cart.map((line) => ({
        product_id: line.product.id,
        quantity: line.quantity,
        discount: line.discount || 0,
        ...(line.product.is_dual_priced && line.priceTier ? { price_tier: line.priceTier } : {}),
      })),
    };
  }

  async function holdCurrentSale() {
    if (!cart.length) return;
    setStatus("submitting");
    setMessage("");
    try {
      await holdSale(currentCartPayload());
      setCart([]);
      setCustomerId(null);
      setPaymentLines([]);
      setInvoiceDiscount("");
      setActiveHeldSaleId(null);
      setStatus("success");
      setMessage(t("saleHeldMessage"));
      loadHeldSales();
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : t("apiError"));
    }
  }

  /** Rehydrate a held invoice's cart from its stored line items, then let
   * the cashier complete it through the normal checkout() path — the
   * held draft is discarded server-side since it's superseded by whatever
   * new sale eventually gets created (or simply abandoned again). */
  function resumeHeldSale(sale: Sale) {
    const rebuiltCart = sale.items
      .map((item): CartLine | null => {
        const product = products.find((p) => p.id === item.product_id);
        if (!product) return null;
        return {
          product,
          quantity: Number(item.quantity),
          priceTier: item.price_tier,
          discount: Number(item.discount) || undefined,
        };
      })
      .filter((line): line is CartLine => line !== null);

    setCart(rebuiltCart);
    setCustomerId(sale.customer_id);
    // A held sale never has payment lines (hold_sale() ignores payment
    // entirely) — nothing to restore here, the cashier picks it fresh.
    setPaymentLines([]);
    setInvoiceDiscount(Number(sale.discount) > 0 ? String(sale.discount) : "");
    setStatus("idle");
    setMessage("");
    setTab("checkout");
    setActiveHeldSaleId(sale.id);
    setHeldSales((current) => current.filter((item) => item.id !== sale.id));
    resumeSale(sale.id).catch(() => {});
  }

  /** Clicking a held-invoice tab: if the cart already has unsaved contents
   * that aren't this same invoice, hold them first (mirroring the manual
   * hold button) so switching tabs never silently discards what the
   * cashier was in the middle of entering — then resume the clicked one. */
  async function handleHeldTabClick(sale: Sale) {
    if (activeHeldSaleId === sale.id) return;
    if (cart.length > 0) {
      try {
        await holdSale(currentCartPayload());
      } catch (error) {
        setStatus("error");
        setMessage(error instanceof Error ? error.message : t("apiError"));
        return;
      }
    }
    resumeHeldSale(sale);
    loadHeldSales();
  }

  /** The "×" on a tab: discards that held invoice outright (never resumed)
   * via the same cancellation path used on the فاکتورهای معلق page —
   * no orphaned DRAFT rows left behind. */
  async function handleDiscardHeldTab(sale: Sale) {
    try {
      await discardSale(sale.id);
      setHeldSales((current) => current.filter((item) => item.id !== sale.id));
      if (activeHeldSaleId === sale.id) setActiveHeldSaleId(null);
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : t("apiError"));
    }
  }

  if (receipt) {
    return (
      <>
        {loyaltyPrompt && (
          <PostCheckoutLoyaltyPrompt prompt={loyaltyPrompt} onDismiss={() => setLoyaltyPrompt(null)} />
        )}
        <ReceiptView
          receipt={receipt}
          onNewSale={() => {
            setReceipt(null);
            setLoyaltyPrompt(null);
          }}
          extraAction={
            loyaltyPrompt?.type === "suggest" ? (
              <QuickAddLoyaltyCustomerButton
                saleTotal={loyaltyPrompt.saleTotal}
                onCustomerCreated={(customer) => {
                  setCustomers((current) => [...current, customer]);
                  setLoyaltyPrompt(null);
                }}
              />
            ) : undefined
          }
        />
      </>
    );
  }

  if (viewingSaleId !== null) {
    return <SaleDetailView saleId={viewingSaleId} onBack={() => setViewingSaleId(null)} />;
  }

  return (
    <main className="main-content">
      <header className="page-header">
        <div>
          <p className="eyebrow">{t("sales")}</p>
          <h1>{t("posTitle")}</h1>
          <p>{t("posSubtitle")}</p>
        </div>
        <CashierShiftBar />
      </header>

      <div className="tabs" role="tablist">
        <button
          className={`tab ${tab === "checkout" ? "active" : ""}`}
          role="tab"
          aria-selected={tab === "checkout"}
          onClick={() => setTab("checkout")}
        >
          <ShoppingCart size={16} /> {t("posTitle")}
        </button>
        <button
          className={`tab ${tab === "held" ? "active" : ""}`}
          role="tab"
          aria-selected={tab === "held"}
          onClick={() => setTab("held")}
        >
          <PauseCircle size={16} /> {t("heldSales")}
        </button>
        <button
          className={`tab ${tab === "history" ? "active" : ""}`}
          role="tab"
          aria-selected={tab === "history"}
          onClick={() => setTab("history")}
        >
          <History size={16} /> {t("invoiceHistory")}
        </button>
      </div>

      {message && (
        <div className={`feedback-banner ${status}`}>
          {status === "success" && <CheckCircle2 size={18} />}
          {message}
        </div>
      )}

      {tab === "history" ? (
        <SalesHistoryTab onSelect={setViewingSaleId} />
      ) : tab === "held" ? (
        <HeldSalesTab onResume={resumeHeldSale} />
      ) : (
      <section className="workspace-grid">
        <article className="panel product-browser">
          <label className="search-field">
            <Search size={18} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("searchProducts")}
            />
          </label>
          <div className="product-grid">
            {filteredProducts.map((product) => {
              const stockStatus = getStockStatus(
                Number(product.stock_quantity),
                Number(product.low_stock_threshold) || 0,
              );
              return (
                <button
                  className="product-tile"
                  key={product.id}
                  onClick={() => addProduct(product)}
                  disabled={Number(product.stock_quantity) <= 0}
                >
                  <span className="product-tile-icon">{product.name.charAt(0)}</span>
                  <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <strong>{product.name}</strong>
                    {product.is_dual_priced && (
                      <span className="dual-price-badge">
                        <Layers size={13} /> {t("dualPriceBadge")}
                      </span>
                    )}
                    {stockStatus !== "ok" && (
                      <span
                        className={`stock-dot ${stockStatus}`}
                        title={stockStatus === "zero" ? t("outOfStock") : t("lowStock")}
                      />
                    )}
                  </span>
                  <small>{t("available")}: {number(Number(product.stock_quantity))}</small>
                  <span>
                    {money(
                      Number(
                        product.is_dual_priced
                          ? product.old_sale_price ?? product.sale_price
                          : product.sale_price,
                      ),
                    )}
                    {product.is_dual_priced ? ` – ${money(Number(product.sale_price))}` : ""}
                  </span>
                  <span className="tile-add"><Plus size={15} /> {t("add")}</span>
                </button>
              );
            })}
          </div>
        </article>

        <aside className="panel cart-panel">
          {heldSales.length > 0 && (
            <div className="held-invoice-tabs">
              {heldSales.map((sale, index) => {
                const customerName = sale.customer_id
                  ? customers.find((c) => c.id === sale.customer_id)?.full_name
                  : null;
                return (
                  <div
                    key={sale.id}
                    className={`held-invoice-tab ${activeHeldSaleId === sale.id ? "active" : ""}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => handleHeldTabClick(sale)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        handleHeldTabClick(sale);
                      }
                    }}
                  >
                    <span className="held-invoice-tab-label">
                      {customerName || `${t("invoice")} ${number(index + 1)}`}
                    </span>
                    <span className="held-invoice-tab-meta">
                      {number(sale.items.length)} {t("items")}
                    </span>
                    <button
                      type="button"
                      className="held-invoice-tab-close"
                      aria-label={t("discardSale")}
                      title={t("discardSale")}
                      onClick={(event) => {
                        event.stopPropagation();
                        handleDiscardHeldTab(sale);
                      }}
                    >
                      <X size={12} />
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          <div className="panel-heading">
            <div>
              <p className="eyebrow">{t("sales")}</p>
              <h2>{t("cart")}</h2>
            </div>
            <span className="count-badge">{number(cart.length)}</span>
          </div>

          <div className="cart-lines">
            {cart.map((line) => {
              const discountOpen = expandedDiscounts.has(line.product.id);
              return (
              <div className="cart-line animated-line" key={line.product.id}>
                <div className="quantity-control compact">
                  <button onClick={() => updateQuantity(line.product.id, -1)}>
                    <Minus size={12} />
                  </button>
                  <span>{number(line.quantity)}</span>
                  <button onClick={() => updateQuantity(line.product.id, 1)}>
                    <Plus size={12} />
                  </button>
                </div>
                <div className="cart-line-info">
                  <strong>{line.product.name}</strong>
                  <small>{money(lineUnitPrice(line))}</small>
                </div>
                <div className="cart-line-actions">
                  {!!line.discount && !discountOpen && (
                    <span className="discount-badge">-{money(line.discount)}</span>
                  )}
                  <button
                    type="button"
                    className={`icon-button tiny ${line.discount ? "has-discount" : ""}`}
                    onClick={() => toggleDiscountInput(line.product.id)}
                    title={t("itemDiscount")}
                    aria-label={t("itemDiscount")}
                  >
                    <Tag size={13} />
                  </button>
                  <button
                    className="icon-button tiny danger"
                    onClick={() =>
                      setCart((current) =>
                        current.filter((item) => item.product.id !== line.product.id),
                      )
                    }
                    aria-label={t("remove")}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>

                {discountOpen && (
                  <div className="cart-line-discount" style={{ gridColumn: "1 / -1" }}>
                    <span>{t("itemDiscount")}</span>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={line.discount || ""}
                      onChange={(event) => updateItemDiscount(line.product.id, event.target.value)}
                      placeholder="0"
                      autoFocus
                    />
                  </div>
                )}

                {line.product.is_dual_priced && (
                  <div className="price-tier-toggle" style={{ gridColumn: "1 / -1" }}>
                    <button
                      type="button"
                      className={`price-tier-button ${line.priceTier === "old" ? "price-tier-selected" : ""}`}
                      onClick={() => setPriceTier(line.product.id, "old")}
                    >
                      <span className="tier-label">{t("dualPriceOldPrice")}</span>
                      <span className="tier-price">
                        {money(Number(line.product.old_sale_price ?? line.product.sale_price))}
                      </span>
                    </button>
                    <button
                      type="button"
                      className={`price-tier-button ${line.priceTier === "new" ? "price-tier-selected" : ""}`}
                      onClick={() => setPriceTier(line.product.id, "new")}
                    >
                      <span className="tier-label">{t("dualPriceNewPrice")}</span>
                      <span className="tier-price">{money(Number(line.product.sale_price))}</span>
                    </button>
                  </div>
                )}
              </div>
              );
            })}
            {!cart.length && (
              <div className="empty-state">
                <ShoppingCart size={28} />
                <span>{t("emptyCart")}</span>
              </div>
            )}
          </div>

          <label className="field">
            <span>{t("invoiceDiscount")}</span>
            <input
              type="number"
              min="0"
              step="0.01"
              value={invoiceDiscount}
              onChange={(event) => setInvoiceDiscount(event.target.value)}
              placeholder="0"
            />
          </label>

          <label className="field">
            <span>{t("customer")}{remainingAfterPayment > 0 ? " *" : ` (${t("optional")})`}</span>
            <CustomerCombobox value={customerId} customers={customers} onChange={setCustomerId} />
          </label>

          {loyaltyBalance && loyaltyBalance.points_balance > 0 && (
            <div className="loyalty-checkout-banner">
              <span>
                {t("customerHasPoints")
                  .replace("{points}", number(loyaltyBalance.points_balance))
                  .replace("{value}", money(Number(loyaltyBalance.points_value_toman)))}
              </span>
              {loyaltyBalance.max_redeemable_points > 0 && (
                <label className="field loyalty-redeem-field">
                  <span>{t("redeemPoints")} ({t("upTo")} {number(loyaltyBalance.max_redeemable_points)})</span>
                  <input
                    type="number"
                    min="0"
                    max={loyaltyBalance.max_redeemable_points}
                    step="1"
                    value={redeemPoints}
                    onChange={(event) => setRedeemPoints(event.target.value)}
                    placeholder="0"
                  />
                </label>
              )}
            </div>
          )}

          {/* Payment breakdown — split across cash/card/check lines, mirroring Purchases.tsx */}
          <div className="payment-lines-panel">
            <div className="payment-lines-header">
              <span>
                <Wallet size={16} />
                {t("paymentLinesTitle")}
              </span>
              <button type="button" className="secondary-button" onClick={addPaymentLine}>
                <Plus size={16} />
                {t("addPaymentLine")}
              </button>
            </div>

            {paymentLines.length === 0 && <p className="payment-lines-empty">{t("paymentLinesEmptyHint")}</p>}

            {paymentLines.map((line) => (
              <div className="payment-line-row" key={line.key}>
                <select
                  value={line.method}
                  onChange={(event) => updatePaymentLine(line.key, { method: event.target.value as PaymentLine["method"] })}
                >
                  <option value="cash">{t("cash")}</option>
                  <option value="card">{t("card")}</option>
                  <option value="check">{t("check")}</option>
                </select>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={line.amount || ""}
                  placeholder={t("amount")}
                  onChange={(event) => updatePaymentLine(line.key, { amount: parseNumeric(event.target.value) })}
                />
                {line.method === "check" && (
                  <>
                    <input
                      type="text"
                      value={line.checkNumber}
                      placeholder={t("checkNumber")}
                      onChange={(event) => updatePaymentLine(line.key, { checkNumber: event.target.value })}
                    />
                    <input
                      type="text"
                      value={line.checkBankName}
                      placeholder={t("checkBankName")}
                      onChange={(event) => updatePaymentLine(line.key, { checkBankName: event.target.value })}
                    />
                    <JalaliDatePicker
                      value={line.checkDueDate}
                      onChange={(isoDate) => updatePaymentLine(line.key, { checkDueDate: isoDate })}
                      placeholder={t("checkDueDate")}
                    />
                  </>
                )}
                <button
                  type="button"
                  className="icon-button danger"
                  onClick={() => removePaymentLine(line.key)}
                  aria-label={t("remove")}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}

            {paymentLines.length > 0 && (
              <div className="payment-lines-summary">
                <span>
                  {t("paidAmount")}: <strong>{money(paidTotal)}</strong>
                </span>
                <span>
                  {t("remainingBalance")}:{" "}
                  <strong className={paymentExceedsTotal ? "overpaid" : ""}>{money(remainingAfterPayment)}</strong>
                </span>
              </div>
            )}
          </div>

          {(itemDiscountsTotal > 0 || invoiceDiscountValue > 0) && (
            <>
              <div className="receipt-preview-row">
                <span>{t("subtotal")}</span>
                <span>{money(subtotalBeforeDiscount)}</span>
              </div>
              <div className="receipt-preview-row">
                <span>{t("discount")}</span>
                <span>-{money(itemDiscountsTotal + invoiceDiscountValue)}</span>
              </div>
            </>
          )}

          <div className="total-row">
            <span>{t("total")}</span>
            <strong>{money(total)}</strong>
          </div>
          <div className="checkout-actions">
            <button
              type="button"
              className="secondary-button"
              disabled={!cart.length || status === "submitting"}
              onClick={holdCurrentSale}
            >
              <PauseCircle size={16} /> {t("holdSale")}
            </button>
            <button
              className={`primary-button submit-button ${status === "submitting" ? "is-loading" : ""}`}
              disabled={
                !cart.length ||
                status === "submitting" ||
                paymentExceedsTotal ||
                hasIncompleteCheckLine ||
                (remainingAfterPayment > 0 && !customerId)
              }
              onClick={() => checkout()}
            >
              {status === "submitting" ? t("loading") : t("checkout")}
            </button>
          </div>
        </aside>
      </section>
      )}

      {creditLimitError && (
        <Modal onClose={() => setCreditLimitError(null)}>
          <div
            className="party-form"
            style={{ width: "min(420px, 100%)" }}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="panel-heading">
              <h2>{t("creditLimitExceededTitle")}</h2>
              <button
                className="icon-button"
                onClick={() => setCreditLimitError(null)}
                aria-label={t("cancel")}
              >
                <X size={18} />
              </button>
            </div>

            <p>{t("creditLimitExceededBody")}</p>

            <div className="total-row">
              <span>{t("creditLimitCurrentBalance")}</span>
              <strong>{money(creditLimitError.currentBalance)}</strong>
            </div>
            <div className="total-row">
              <span>{t("creditLimitLimit")}</span>
              <strong>{money(creditLimitError.creditLimit)}</strong>
            </div>
            <div className="total-row">
              <span>{t("creditLimitPortion")}</span>
              <strong>{money(creditLimitError.creditPortion)}</strong>
            </div>

            {canOverride && <p className="muted-text">{t("creditLimitOverridePrompt")}</p>}

            <div className="form-actions">
              <button className="secondary-button" onClick={() => setCreditLimitError(null)}>
                {t("cancel")}
              </button>
              {canOverride && (
                <button
                  className={`primary-button ${status === "submitting" ? "is-loading" : ""}`}
                  onClick={() => checkout({ creditOverride: true })}
                >
                  {t("creditLimitOverrideConfirm")}
                </button>
              )}
            </div>
          </div>
        </Modal>
      )}
    </main>
  );
}
