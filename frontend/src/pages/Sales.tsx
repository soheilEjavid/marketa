import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  History,
  Layers,
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
import { AmountInput } from "../components/AmountInput";
import { useI18n } from "../i18n";
import { canOverrideCreditLimit } from "../permissions";
import { getSession } from "../session";
import type { Customer, LoyaltyBalance, Product, Sale, SalePaymentMethod } from "../types";
import { CashierShiftBar } from "../components/CashierShiftBar";
import { CustomerCombobox } from "../components/CustomerCombobox";
import { HeldSalesTab } from "../components/HeldSalesTab";
import { Modal } from "../components/Modal";
import { PostCheckoutLoyaltyPrompt, type PostCheckoutLoyaltyPrompt as PostCheckoutLoyaltyPromptType } from "../components/PostCheckoutLoyaltyPrompt";
import { QuickAddLoyaltyCustomerButton } from "../components/QuickAddLoyaltyCustomerButton";
import { ReceiptView, type ReceiptData } from "../components/ReceiptView";
import { SalesHistoryTab } from "../components/SalesHistoryTab";
import { SaleDetailView } from "../components/SaleDetailView";
import { QuantityInput } from "../components/QuantityInput";
import { formatQuantity, roundToWeightPrecision } from "../lib/quantity";
import { getStockStatus } from "../lib/stockStatus";

type PaymentLine = {
  key: number;
  method: SalePaymentMethod;
  amount: number;
  /** True while `amount` is still the system-suggested default the line was
   * created or last auto-balanced with — never yet hand-typed by the
   * cashier. Only a line still in this state may be auto-adjusted when the
   * other split-payment line changes (see updatePaymentLine); once the
   * cashier types a real amount, that's a deliberate choice (e.g. paying
   * part now and leaving the rest as نسیه) and must never be silently
   * overwritten. */
  autoAmount?: boolean;
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
  const { money, number, t, locale, direction } = useI18n();
  /**
   * The scanner is a keyboard: it types the barcode and presses Enter, into
   * whatever happens to have focus. So the search box has to *hold* focus
   * between scans — a cashier working a queue never touches the mouse, and
   * a scan that lands in a discount box or nowhere at all is worse than no
   * scanner, because it looks like it worked.
   */
  const searchInputRef = useRef<HTMLInputElement>(null);
  const paymentSectionRef = useRef<HTMLDivElement>(null);
  /**
   * Which leg of the keyboard checkout has the keyboard.
   *
   * A cashier working a queue never touches the mouse: scan, scan, Enter to
   * say "done scanning", Enter to take the money, Enter to start the next
   * customer. Enter means something different at each of those points, so
   * the screen has to say which one it is on — hence the ring drawn around
   * the active panel. The receipt is its own leg and is driven by `receipt`
   * rather than this, since that view replaces the whole page.
   */
  const [stage, setStage] = useState<"scan" | "payment">("scan");
  /** Bumped whenever the keyboard should land on the chosen tender pill —
   * entering the payment stage, or stepping with the arrows. Focus follows
   * in a layout effect so it runs after React has painted the pill it is
   * aiming at, which a requestAnimationFrame does not guarantee. */
  const [pillFocusToken, setPillFocusToken] = useState(0);
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
  /** Product ids whose dual-price old/new toggle is currently expanded.
   * Collapsed by default (and re-collapsed after picking a tier) so a
   * dual-priced cart line normally shows just the active price, not two
   * full-size buttons — same reveal-on-demand pattern as expandedDiscounts. */
  const [expandedPriceTiers, setExpandedPriceTiers] = useState<Set<number>>(new Set());
  /** Whether the invoice-discount input is revealed — collapsed to a small
   * "+ add" link by default (most sales have no invoice-level discount),
   * same reveal-on-demand idea as the two Sets above. */
  const [invoiceDiscountOpen, setInvoiceDiscountOpen] = useState(false);
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

  /** Hand the keyboard back to the scanner. */
  const focusSearch = useCallback(() => {
    setStage("scan");
    // A frame later, so it wins against whatever is closing: a modal
    // restoring focus to its trigger, a freshly-rendered cart line, the
    // autoFocus on a discount box.
    requestAnimationFrame(() => searchInputRef.current?.focus());
  }, []);

  // Ready to scan the moment the checkout is on screen, and again whenever
  // the thing that took the keyboard away has finished: a receipt printed, a
  // credit-limit warning dismissed, a loyalty prompt closed, a held sale
  // resumed. Each of these ends with the cashier facing an empty or reloaded
  // cart and the next customer already putting things on the counter.
  useEffect(() => {
    if (tab !== "checkout") return;
    if (receipt || creditLimitError || loyaltyPrompt || viewingSaleId) return;
    focusSearch();
  }, [tab, receipt, creditLimitError, loyaltyPrompt, viewingSaleId, focusSearch]);

  // Put the keyboard on the chosen tender pill once React has actually
  // painted it. Land on the selected one so the arrows step from what the
  // cashier is looking at; asking for any button instead would catch "add
  // another payment line", which sits earlier in the DOM.
  useLayoutEffect(() => {
    if (!pillFocusToken || stage !== "payment") return;
    const section = paymentSectionRef.current;
    const target =
      section?.querySelector<HTMLElement>(".payment-line-row .price-tier-selected") ??
      section?.querySelector<HTMLElement>(".payment-line-row .price-tier-button");
    (target ?? section)?.focus();
  }, [pillFocusToken, stage]);

  // Enter on the receipt starts the next customer — the same thing the
  // "فروش جدید" button does. Bound to the document rather than to a node
  // because the receipt view has no single element that reliably holds
  // focus, and there is nothing else on screen for Enter to mean here.
  useEffect(() => {
    if (!receipt) return;
    function handleKey(event: KeyboardEvent) {
      if (event.key !== "Enter") return;
      // Unless the cashier is on the print button and means to press it.
      if (document.activeElement instanceof HTMLButtonElement) return;
      event.preventDefault();
      setReceipt(null);
      setLoyaltyPrompt(null);
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [receipt]);

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

  /**
   * Why the sale cannot be rung up yet, or null when it can.
   *
   * The submit button has always known this — it just expressed it as a
   * `disabled` expression, which tells a cashier nothing. Naming each
   * reason lets the Enter key say what is wrong instead of doing nothing,
   * and keeps the button and the keyboard path on one rule rather than two
   * that can drift.
   */
  const checkoutBlockedReason: string | null =
    !cart.length
      ? t("cartEmptyHint")
      : status === "submitting"
        ? t("loading")
        : paymentExceedsTotal
          ? t("paymentExceedsTotal")
          : remainingAfterPayment > 0 && !customerId
            ? t("creditNeedsCustomer")
            : null;
  // Which single method (if any) all entered payment lines share so far —
  // used to name the covering method for the remaining-balance hint below
  // (e.g. "card entered -> remainder collected in cash"). Ambiguous once
  // both methods are in use, so no suggestion is shown in that case.
  const usedPaymentMethods = new Set(
    paymentLines.filter((line) => line.amount > 0).map((line) => line.method),
  );
  const suggestedRemainderMethod: PaymentLine["method"] | null =
    usedPaymentMethods.size === 1 ? (usedPaymentMethods.has("card") ? "cash" : "card") : null;

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
      // Defaults to card (most purchases are made by card) and to whatever
      // is still owed right now — remainingAfterPayment already equals the
      // full invoice total when this is the first line (no prior lines to
      // subtract), and the true remainder after that. Saves re-typing the
      // total for the common single-full-payment case; still freely
      // editable for a split payment.
      { key: nextPaymentLineKey++, method: "card", amount: remainingAfterPayment, autoAmount: true, checkNumber: "", checkBankName: "", checkDueDate: "", notes: "" },
    ]);
  }

  function updatePaymentLine(key: number, changes: Partial<PaymentLine>) {
    setPaymentLines((current) => {
      // Typing a real amount into the line the cashier is directly editing
      // always marks it manual — it's never auto-balanced again after this.
      const updated = current.map((line) =>
        line.key === key
          ? { ...line, ...changes, ...(changes.amount !== undefined ? { autoAmount: false } : {}) }
          : line,
      );
      // Auto-balance the other line when there are exactly two split-payment
      // lines and an amount was just typed — e.g. total 20,000: typing
      // 10,000 into the cash line sets the card line to the remaining
      // 10,000 automatically, instead of making the cashier do that
      // subtraction by hand so the two lines still sum to the total. But
      // only while that other line is still at its system-suggested amount
      // (autoAmount !== false) — once the cashier has hand-typed a real
      // amount into it (e.g. "10,000 by card, 5,000 cash, the remaining
      // 5,000 stays نسیه"), it's a deliberate partial payment and must never
      // be silently overwritten just because the other line changed. Only
      // the two-line case: with 3+ lines there's no single unambiguous
      // "other" line to adjust, so those are left for the cashier to enter.
      if (changes.amount !== undefined && updated.length === 2) {
        const otherIndex = updated.findIndex((line) => line.key !== key);
        if (otherIndex !== -1 && updated[otherIndex].autoAmount !== false) {
          const editedAmount = Number(changes.amount) || 0;
          updated[otherIndex] = { ...updated[otherIndex], amount: Math.max(0, total - editedAmount), autoAmount: true };
        }
      }
      return updated;
    });
  }

  function removePaymentLine(key: number) {
    setPaymentLines((current) => current.filter((line) => line.key !== key));
  }

  function addProduct(product: Product) {
    setStatus("idle");
    setCart((current) => {
      const existing = current.find((line) => line.product.id === product.id);
      if (existing) {
        // A weighted product is deliberately not incremented on a repeat
        // scan: "+1" would mean +1 kg, which is a guess at what is on the
        // scale, and a wrong one worth real money. The line stays as it is
        // and the cashier types the weight.
        if (product.is_weighted) return current;
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
    // Clicking a tile leaves the keyboard on that button, so the next scan
    // would go nowhere. Put it back regardless of how the item was added.
    focusSearch();
  }

  /**
   * Enter in the search box. A barcode scanner is just a keyboard that types
   * fast and finishes with Enter, so the only thing that tells a scan apart
   * from a cashier typing is that the text is *exactly* somebody's barcode.
   * That is enough, and it is reliable — unlike timing the keystrokes, which
   * guesses at hardware and gets it wrong on a slow USB hub or a fast typist.
   *
   * An exact hit adds the product and clears the box for the next scan.
   * Anything else falls through to the filtered grid exactly as before, so
   * typing part of a product name still works the way it always has.
   */
  function handleSearchKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key !== "Enter") return;
    const scanned = query.trim();

    // Enter on an empty box is the cashier saying "that's everything" — not
    // a scan of nothing. No lookup is attempted; the keyboard moves on to
    // taking the money. With an empty cart there is nothing to move on to,
    // so it does nothing at all rather than opening a payment line for a
    // sale that does not exist yet.
    if (!scanned) {
      if (!cart.length) return;
      event.preventDefault();
      goToPayment();
      return;
    }

    const matches = products.filter((product) => product.barcode === scanned);
    if (matches.length === 0) return; // not a barcode — leave the grid filtered

    event.preventDefault();

    // Barcodes are unique in the database, so this is a "cannot happen" —
    // which is exactly why it must not silently pick one and charge for the
    // wrong thing. Name them and let the cashier choose from the grid.
    if (matches.length > 1) {
      setStatus("error");
      setMessage(`${t("duplicateBarcodeWarning")} ${matches.map((p) => p.name).join("، ")}`);
      return;
    }

    // Straight through addProduct, so the scan path inherits its stock rules
    // rather than growing a second copy of them.
    addProduct(matches[0]);
    setQuery("");
    focusSearch();
  }

  /**
   * Hand the keyboard to the payment section, opening a line if there is
   * none.
   *
   * Without that line there is nothing in the payment area but a link, no
   * method is chosen, and the submit button is disabled — an empty payment
   * section means a credit sale, which needs a customer. So "Enter, Enter"
   * would dead-end on the very sale it is meant to speed up: a walk-in
   * paying now. The line it opens is the ordinary one addPaymentLine()
   * makes by hand — card, for the whole remaining amount — so the keyboard
   * path and the mouse path produce the same invoice.
   */
  function goToPayment() {
    if (!paymentLines.length) addPaymentLine();
    setStage("payment");
    // Focusing happens in the effect below, not here: the payment line this
    // may have just opened does not exist in the DOM yet, and a
    // requestAnimationFrame can still run before React has painted it —
    // which left the keyboard on nothing and the first arrow press doing
    // nothing.
    setPillFocusToken((token) => token + 1);
  }

  /** Order of the method pills as they are rendered. */
  const PAYMENT_METHODS: SalePaymentMethod[] = ["cash", "card", "card_to_card"];

  /**
   * Left/right step through نقدی / کارت / کارت به کارت.
   *
   * The arrows follow the eye, not the DOM: the layout flips with the
   * language, so in the Persian (RTL) interface the pill to the *left* of
   * the current one is the next in order, and in English it is the
   * previous. Getting that backwards would have the selection crawl the
   * wrong way down the row, which is the sort of thing that reads as a
   * broken keyboard rather than a convention.
   */
  function stepPaymentMethod(event: React.KeyboardEvent<HTMLDivElement>) {
    if (!paymentLines.length) return;
    // The line the cashier is actually on, or the only one there is.
    const row = (document.activeElement as HTMLElement | null)?.closest(".payment-line-row");
    const rows = Array.from(document.querySelectorAll(".payment-line-row"));
    const line = paymentLines[row ? Math.max(0, rows.indexOf(row)) : 0];
    if (!line) return;

    const forward = direction === "rtl" ? event.key === "ArrowLeft" : event.key === "ArrowRight";
    const current = PAYMENT_METHODS.indexOf(line.method);
    const next = PAYMENT_METHODS[
      (current + (forward ? 1 : PAYMENT_METHODS.length - 1)) % PAYMENT_METHODS.length
    ];
    updatePaymentLine(line.key, { method: next });
    // Keep the keyboard on the pill that is now selected, so the next arrow
    // steps from where the cashier is looking. Same reason as goToPayment:
    // the selected class moves on the next render, so the focus has to wait
    // for it rather than race it.
    setPillFocusToken((token) => token + 1);
  }

  /** Enter finalizes, Esc goes back to scanning, arrows pick the tender. */
  function handlePaymentKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      stepPaymentMethod(event);
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      // Deliberately leaves the cart, the payment line and any typed amount
      // exactly as they are — the cashier is stepping back to scan one more
      // item, not abandoning the sale.
      focusSearch();
      return;
    }
    if (event.key !== "Enter") return;
    // A method pill or the remove button would otherwise fire its own click
    // on Enter, silently changing the payment instead of submitting it.
    event.preventDefault();

    if (checkoutBlockedReason) {
      // Say what is missing and stay put, so the cashier can fix it and
      // press Enter again without re-entering anything.
      setStatus("error");
      setMessage(checkoutBlockedReason);
      return;
    }
    checkout();
  }

  function setPriceTier(productId: number, tier: "old" | "new") {
    setCart((current) =>
      current.map((line) =>
        line.product.id === productId ? { ...line, priceTier: tier } : line,
      ),
    );
    // Collapse back to the compact single-price view once a tier is picked —
    // re-expand via togglePriceTierInput if the cashier needs to switch again.
    setExpandedPriceTiers((current) => {
      if (!current.has(productId)) return current;
      const next = new Set(current);
      next.delete(productId);
      return next;
    });
  }

  function togglePriceTierInput(productId: number) {
    setExpandedPriceTiers((current) => {
      const next = new Set(current);
      if (next.has(productId)) {
        next.delete(productId);
      } else {
        next.add(productId);
      }
      return next;
    });
  }

  function updateItemDiscount(productId: number, value: number) {
    setCart((current) =>
      current.map((line) =>
        line.product.id === productId
          ? { ...line, discount: Number.isNaN(value) ? 0 : Math.max(0, value) }
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

  /**
   * Set a cart line to an absolute quantity, capped at available stock.
   * Both the counted stepper and the weighted field arrive here — they
   * differ in how the cashier picks a number, not in what happens to it.
   *
   * A line that reaches zero is removed, which is how the stepper has
   * always cleared a line. A weighted line is exempt: clearing the field
   * to retype the weight would otherwise delete the line mid-keystroke.
   */
  function setLineQuantity(productId: number, quantity: number) {
    setCart((current) =>
      current
        .map((line) => {
          if (line.product.id !== productId) return line;
          const capped = Math.min(quantity, Number(line.product.stock_quantity));
          return {
            ...line,
            quantity: line.product.is_weighted ? roundToWeightPrecision(capped) : capped,
          };
        })
        .filter((line) => line.product.is_weighted || line.quantity > 0),
    );
  }

  async function checkout(options?: { creditOverride?: boolean }) {
    if (!cart.length) return;
    if (remainingAfterPayment > 0 && !customerId) {
      setStatus("error");
      setMessage(t("customerRequiredForCredit"));
      return;
    }
    if (paymentExceedsTotal) return;
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
          isWeighted: line.product.is_weighted,
          unit: line.product.unit,
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
        <article className={`panel product-browser ${stage === "scan" ? "stage-active" : ""}`}>
          <label className="search-field">
            <Search size={18} />
            <input
              ref={searchInputRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={handleSearchKeyDown}
              placeholder={t("searchOrScan")}
              autoComplete="off"
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
                  <span
                    className="product-tile-icon"
                    style={
                      product.image_url
                        ? { backgroundImage: `url(${product.image_url})`, backgroundSize: "cover" }
                        : undefined
                    }
                  >
                    {!product.image_url && product.name.charAt(0)}
                  </span>
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
                  <small>
                    {t("available")}:{" "}
                    {formatQuantity(
                      Number(product.stock_quantity),
                      product.is_weighted,
                      locale,
                      number,
                    )}
                    {product.unit ? ` ${product.unit}` : ""}
                  </small>
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

        <aside className={`panel cart-panel ${stage === "payment" ? "stage-active" : ""}`}>
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

          {/* "فروش" + "سبد فروش" combined onto one line (was eyebrow above,
              h2 below — two lines) specifically to free up a bit more
              vertical space in the cart panel for cart-line rows, same
              motivation as every other compactness change on this panel. */}
          <div className="panel-heading cart-heading-compact">
            <h2><span className="eyebrow">{t("sales")}</span> {t("cart")}</h2>
            <span className="count-badge">{number(cart.length)}</span>
          </div>

          {/* Scrollable middle zone — everything here can legitimately grow
              (cart size, payment lines) and scrolls together as one unit,
              so it never pushes the fixed footer below (checkout-actions
              etc.) out of view. See .cart-fixed-footer further down. */}
          <div className="cart-scroll-zone">
          <div className="cart-lines">
            {cart.map((line) => {
              const discountOpen = expandedDiscounts.has(line.product.id);
              const priceTierOpen = expandedPriceTiers.has(line.product.id);
              return (
              <div className="cart-line animated-line compact-row" key={line.product.id}>
                <div
                  className="product-avatar cart-line-avatar"
                  style={
                    line.product.image_url
                      ? { backgroundImage: `url(${line.product.image_url})`, backgroundSize: "cover" }
                      : undefined
                  }
                >
                  {!line.product.image_url && line.product.name.charAt(0)}
                </div>
                <div className="cart-line-info">
                  <strong>{line.product.name}</strong>
                  <span className="cart-line-price-row">
                    <small>{money(lineUnitPrice(line))}</small>
                    {line.product.is_dual_priced && !priceTierOpen && (
                      <button
                        type="button"
                        className="price-tier-collapsed"
                        onClick={() => togglePriceTierInput(line.product.id)}
                        title={t("dualPriceBadge")}
                      >
                        {line.priceTier === "old" ? t("dualPriceOldPrice") : t("dualPriceNewPrice")}
                        <ChevronDown size={11} />
                      </button>
                    )}
                    {!!line.discount && !discountOpen && (
                      <span className="discount-badge">-{money(line.discount)}</span>
                    )}
                  </span>
                </div>
                <QuantityInput
                  compact
                  quantity={line.quantity}
                  isWeighted={line.product.is_weighted}
                  unit={line.product.unit}
                  max={Number(line.product.stock_quantity)}
                  onChange={(quantity) => setLineQuantity(line.product.id, quantity)}
                />
                <div className="cart-line-actions">
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
                    <AmountInput
                      min="0"
                      value={line.discount || null}
                      onChange={(discount) => updateItemDiscount(line.product.id, discount ?? 0)}
                      placeholder="0"
                      autoFocus
                    />
                  </div>
                )}

                {line.product.is_dual_priced && priceTierOpen && (
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

          </div>

          {/* Fixed footer — customer, invoice discount, payment section,
              totals, and both checkout actions. Always rendered at natural
              size, never inside the scrollable zone above, so none of it
              can be pushed out of view or clipped regardless of cart size.
              Customer selection in particular used to sit inside the
              scrollable zone (above the cart lines it now follows) and
              would get buried below the last cart line once the cart grew
              past what fit on screen — moved here specifically so it's
              always reachable without scrolling, same reasoning as the
              payment section below it. */}
          <div className="cart-fixed-footer">
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
                  <AmountInput
                    integer
                    currencyAware={false}
                    min="0"
                    max={loyaltyBalance.max_redeemable_points}
                    value={Number(redeemPoints) || null}
                    onChange={(points) => setRedeemPoints(points === null ? "" : String(points))}
                    placeholder="0"
                  />
                </label>
              )}
            </div>
          )}

          {invoiceDiscountOpen || invoiceDiscountValue > 0 ? (
            <label className="field">
              <span>{t("invoiceDiscount")}</span>
              <AmountInput
                min="0"
                value={Number(invoiceDiscount) || null}
                onChange={(discount) => setInvoiceDiscount(discount === null ? "" : String(discount))}
                placeholder="0"
                autoFocus={invoiceDiscountOpen}
              />
            </label>
          ) : (
            <button type="button" className="add-discount-link" onClick={() => setInvoiceDiscountOpen(true)}>
              <Plus size={14} /> {t("invoiceDiscount")}
            </button>
          )}

          {/* Payment breakdown — split across cash/card lines. No check option
              here: this shop doesn't accept checks from customers. Purchases.tsx
              still has cash/card/check for paying suppliers — untouched.
              Collapsed to a single compact link (same idea and styling as
              the invoice-discount link above) when no line has been added
              yet — the common single-full-payment case shouldn't pay for a
              bordered header+hint-text panel it isn't using. The panel
              (with its header, since >=1 line now needs the "add another"
              button and remove controls) only renders once a line exists. */}
          <div
            ref={paymentSectionRef}
            className="payment-stage"
            tabIndex={-1}
            onKeyDown={handlePaymentKeyDown}
            onFocus={() => setStage("payment")}
          >
          {paymentLines.length === 0 ? (
            <div className="payment-collapsed-row">
              <button type="button" className="add-discount-link" onClick={addPaymentLine}>
                <Wallet size={14} /> {t("paymentLinesTitle")}
              </button>
              {/* Explicit "this will be recorded as credit" notice — restores
                  the signal that used to live in the always-rendered empty-
                  state hint text, so a cashier who leaves payment untouched
                  still sees clearly (not just by absence of a field) that the
                  sale is going on the customer's account. */}
              {remainingAfterPayment > 0 && (
                <small className="credit-sale-hint">{t("paymentLinesEmptyHint")}</small>
              )}
            </div>
          ) : (
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

            {paymentLines.map((line) => (
              <div className="payment-line-row" key={line.key}>
                {/* Reuses the existing price-tier-button/price-tier-selected
                    pill pattern (see the dual-price toggle above) instead of
                    a native <select> — same selected-state styling, just a
                    plain single-line label instead of the tier label+price
                    pair. */}
                <div className="payment-method-toggle">
                  <button
                    type="button"
                    className={`price-tier-button ${line.method === "cash" ? "price-tier-selected" : ""}`}
                    onClick={() => updatePaymentLine(line.key, { method: "cash" })}
                  >
                    {t("cash")}
                  </button>
                  <button
                    type="button"
                    className={`price-tier-button ${line.method === "card" ? "price-tier-selected" : ""}`}
                    onClick={() => updatePaymentLine(line.key, { method: "card" })}
                  >
                    {t("card")}
                  </button>
                  <button
                    type="button"
                    className={`price-tier-button ${line.method === "card_to_card" ? "price-tier-selected" : ""}`}
                    onClick={() => updatePaymentLine(line.key, { method: "card_to_card" })}
                  >
                    {t("cardToCard")}
                  </button>
                </div>
                <AmountInput
                  min="0"
                  value={line.amount || null}
                  placeholder={t("amount")}
                  onChange={(amount) => updatePaymentLine(line.key, { amount: amount ?? 0 })}
                />
                <button
                  type="button"
                  className="icon-button tiny danger"
                  onClick={() => removePaymentLine(line.key)}
                  aria-label={t("remove")}
                >
                  <Trash2 size={14} />
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
                  {remainingAfterPayment > 0 && suggestedRemainderMethod && (
                    <small className="remaining-balance-hint">
                      {" "}
                      ({t("collectVia")} {t(suggestedRemainderMethod)})
                    </small>
                  )}
                </span>
              </div>
            )}
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
                (remainingAfterPayment > 0 && !customerId)
              }
              onClick={() => checkout()}
            >
              {status === "submitting" ? t("loading") : t("checkout")}
            </button>
          </div>
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
