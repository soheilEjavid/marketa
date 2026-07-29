import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  ClipboardList,
  FileText,
  History,
  Info,
  PackagePlus,
  Plus,
  ShoppingBag,
  Trash2,
  Upload,
  Wallet,
  XCircle,
} from "lucide-react";

import { ApiError, createPurchase, getProducts, getSuppliers } from "../api";
import type { DualPriceRequiredResponse } from "../api";
import { useI18n } from "../i18n";
import type { ExtractedInvoice, Product, Supplier } from "../types";
import { extractInvoiceData, matchProductName } from "../invoice-scanner";
import { calculateMarginPct, formatMarginPct, getMarginStatus } from "../lib/margin";
import { ProductCombobox } from "../components/ProductCombobox";
import { JalaliDatePicker } from "../components/JalaliDatePicker";
import { DualPriceConfirmModal } from "../components/DualPriceConfirmModal";
import { PurchasesHistoryTab } from "../components/PurchasesHistoryTab";
import { PurchaseDetailView } from "../components/PurchaseDetailView";

type PurchaseLine = {
  key: number;
  productId: number;
  quantity: number;
  unitCost: number;
  sellingPrice?: number | null;
  expiryDate?: string;
  /** کالای امانی — stock still increases, but this line's value stays out
   * of the payable total until settled later (see Reports). */
  isConsignment?: boolean;
  /** اشانتیون — a genuinely free promotional item from the supplier, not
   * an incomplete row. unitCost is left untouched (nothing is ever
   * cleared/lost) — every place that reads cost for calculation,
   * totals, or submission goes through effectiveCost() instead, which
   * treats this line's cost as 0 regardless of whatever's stored. */
  isPromotional?: boolean;
  /** Scanner metadata — only populated when coming from a scan. */
  rawName?: string;
  /** Whether this line had a zero amount at extraction time. */
  isZeroAmount?: boolean;
  /** Whether the product name couldn't be matched to the catalogue. */
  isUnmatched?: boolean;
};

type PaymentLine = {
  key: number;
  method: "cash" | "card" | "check";
  amount: number;
  checkNumber: string;
  checkBankName: string;
  checkDueDate: string;
  notes: string;
};

type ScanPhase = "idle" | "scanning" | "success" | "error";

type LineProfit = {
  profitPerUnit: number;
  marginPct: number;
  lineProfitTotal: number;
  isPromotional: boolean;
};

/** The cost this line actually counts as, for every calculation/total/
 * submission purpose — a promotional (اشانتیون) line is always treated
 * as free regardless of whatever value happens to be sitting in
 * line.unitCost (that value is never cleared, just ignored while
 * checked, so unchecking trivially un-hides it — no separate "stash the
 * old price" bookkeeping needed). */
function effectiveCost(line: PurchaseLine): number {
  return line.isPromotional ? 0 : line.unitCost;
}

/** Live per-line profit for the ویزیتور profit calculator — cost and sale
 * price come straight from the row being typed (existing product or one
 * created in the same instant via quick-add), never persisted data. Uses
 * the exact same calculateMarginPct as lib/margin.ts/Products.tsx; no
 * parallel formula. Returns null (render "—") rather than a misleading
 * number whenever either price is missing/zero/negative — except for a
 * promotional line, where a zero cost is the genuine, intended value,
 * not an incomplete row, so it proceeds straight to the same formula
 * (which divides by sale price, not cost, so 0 cost is not a
 * division-by-zero case — it cleanly resolves to 100%). */
function computeLineProfit(line: PurchaseLine): LineProfit | null {
  const cost = effectiveCost(line);
  const sale = line.sellingPrice;
  if (sale == null || sale <= 0) return null;
  if (!line.isPromotional && cost <= 0) return null;
  const marginPct = calculateMarginPct(sale, cost);
  if (marginPct === null) return null;
  const profitPerUnit = sale - cost;
  return {
    profitPerUnit,
    marginPct,
    lineProfitTotal: profitPerUnit * line.quantity,
    isPromotional: Boolean(line.isPromotional),
  };
}

let nextLineKey = 1;
let nextPaymentLineKey = 1;

export function Purchases() {
  const { money, number, language, t } = useI18n();
  const [products, setProducts] = useState<Product[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [supplierId, setSupplierId] = useState<number>(0);
  const [lines, setLines] = useState<PurchaseLine[]>([
    { key: nextLineKey++, productId: 0, quantity: 1, unitCost: 0, sellingPrice: null, expiryDate: "" },
  ]);
  const [paymentLines, setPaymentLines] = useState<PaymentLine[]>([]);
  const [status, setStatus] = useState<"idle" | "submitting" | "success" | "error">("idle");
  const [message, setMessage] = useState("");
  const [bulkCount, setBulkCount] = useState<string>("1");
  const [dualPriceProducts, setDualPriceProducts] = useState<
    DualPriceRequiredResponse["products"] | null
  >(null);

  // ── Scan state ──────────────────────────────────────────────────────
  const [scanPhase, setScanPhase] = useState<ScanPhase>("idle");
  const [scanError, setScanError] = useState<string>("");
  const [extracted, setExtracted] = useState<ExtractedInvoice | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [tab, setTab] = useState<"entry" | "history">("entry");
  const [viewingPurchaseId, setViewingPurchaseId] = useState<number | null>(null);

  useEffect(() => {
    Promise.all([
      getProducts(),
      getSuppliers(),
    ]).then(([products, suppliers]) => {
      setProducts(products);
      setSuppliers(suppliers);
    }).catch(() => {
      setStatus("error");
      setMessage(t("apiError"));
    });
  }, [t]);

  // A promotional (اشانتیون) line has a genuinely zero cost by design —
  // it must still count as a valid, submittable line (unlike an ordinary
  // row where zero cost just means "not filled in yet").
  const validLines = lines.filter(
    (line) => line.productId && line.quantity > 0 && (line.unitCost > 0 || line.isPromotional),
  );
  // A ویزیتور deal is often evaluated by price alone before the shopkeeper
  // has picked (or bothered creating) a catalog product for it — the
  // running total/profit numbers need to reflect that immediately, not
  // just once a product is attached. Submission (validLines above) still
  // requires a real product; this broader set is display-only.
  const displayLines = lines.filter(
    (line) => line.quantity > 0 && (line.unitCost > 0 || line.isPromotional),
  );
  const total = useMemo(
    () =>
      displayLines.reduce(
        (sum, line) => sum + line.quantity * effectiveCost(line),
        0,
      ),
    [displayLines],
  );
  // Consignment lines still show up in the full invoice total above, but
  // carry no payment obligation yet — payment lines are validated against
  // this payable-only figure, matching the backend's purchase.total.
  const consignmentValue = useMemo(
    () =>
      displayLines
        .filter((line) => line.isConsignment)
        .reduce((sum, line) => sum + line.quantity * effectiveCost(line), 0),
    [displayLines],
  );
  const payableTotal = total - consignmentValue;

  // Whole-invoice profit calculator (see computeLineProfit) — only counts
  // lines where both prices are actually present, so an in-progress row
  // never drags the blended margin toward a misleading number.
  const invoiceProfitSummary = useMemo(() => {
    let revenue = 0;
    let cost = 0;
    let countedLines = 0;
    for (const line of lines) {
      const profit = computeLineProfit(line);
      if (!profit) continue;
      revenue += (line.sellingPrice as number) * line.quantity;
      cost += effectiveCost(line) * line.quantity;
      countedLines += 1;
    }
    if (countedLines === 0) return null;
    return {
      totalProfit: revenue - cost,
      blendedMarginPct: calculateMarginPct(revenue, cost),
    };
  }, [lines]);

  // Master toggle shown above the submit button: reflects whether every
  // current line is already marked consignment, and lets the user flip
  // all of them at once instead of checking each row individually.
  const allLinesConsignment = lines.length > 0 && lines.every((line) => line.isConsignment);

  function toggleAllConsignment(checked: boolean) {
    setLines((current) => current.map((line) => ({ ...line, isConsignment: checked })));
  }

  const paidTotal = useMemo(
    () => paymentLines.reduce((sum, line) => sum + (Number(line.amount) || 0), 0),
    [paymentLines],
  );
  const remainingAfterPayment = Math.max(0, payableTotal - paidTotal);
  const paymentExceedsTotal = paidTotal > payableTotal;
  const hasIncompleteCheckLine = paymentLines.some(
    (line) => line.method === "check" && (!line.checkDueDate || !line.checkNumber.trim()),
  );

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

  // ── Computed warnings ────────────────────────────────────────────────
  const hasZeroAmountLine = lines.some((l) => l.isZeroAmount);
  const hasUnmatchedLine = lines.some((l) => l.isUnmatched);
  const hasTotalMismatch = useMemo(() => {
    if (!extracted) return false;
    const sumOfLines = lines.reduce(
      (s, l) => s + l.quantity * effectiveCost(l),
      0,
    );
    return Math.abs(sumOfLines - extracted.finalTotal) > 100;
  }, [lines, extracted]);

  function updateLine(key: number, changes: Partial<PurchaseLine>) {
    setLines((current) =>
      current.map((line) => (line.key === key ? { ...line, ...changes } : line)),
    );
  }

  function selectProduct(line: PurchaseLine, productId: number) {
    const product = products.find((item) => item.id === productId);
    updateLine(line.key, {
      productId,
      unitCost: product ? Number(product.purchase_price) : 0,
      sellingPrice: product ? Number(product.sale_price) : null,
      // Once user manually selects a product, clear the unmatched flag
      isUnmatched: false,
    });
  }

  /** A brand-new product made via ProductCombobox's "quick add" — used
   * instead of selectProduct() because `products` (fetched once on page
   * load) doesn't contain this product yet, so looking it up by id there
   * would resolve to nothing and silently zero out the cost/sale price
   * the user just typed into the creation form. Also appends it to
   * `products` so the rest of the page (other rows' comboboxes) sees it
   * too, without needing a full refetch. */
  function selectNewlyCreatedProduct(line: PurchaseLine, product: Product) {
    setProducts((current) => [...current, product]);
    updateLine(line.key, {
      productId: product.id,
      unitCost: Number(product.purchase_price),
      sellingPrice: Number(product.sale_price),
      isUnmatched: false,
    });
  }

  function addBulkRows() {
    const count = Math.max(1, Math.min(parseInt(bulkCount) || 1, 50));
    const newLines: PurchaseLine[] = Array.from({ length: count }, () => ({
      key: nextLineKey++,
      productId: 0,
      quantity: 1,
      unitCost: 0,
      sellingPrice: null,
      expiryDate: "",
    }));
    setLines((current) => [...current, ...newLines]);
  }

  function handleBulkCountChange(value: string) {
    setBulkCount(value);
  }

  function handleBulkCountBlur() {
    const num = parseInt(bulkCount);
    if (isNaN(num) || num < 1) {
      setBulkCount("1");
    } else {
      setBulkCount(String(Math.min(num, 50)));
    }
  }

  function parseNumeric(value: string): number {
    const parsed = Number(value);
    return Number.isNaN(parsed) ? 0 : parsed;
  }

  function parseOptionalNumber(value: string): number | null {
    if (!value.trim()) return null;
    const parsed = Number(value);
    return Number.isNaN(parsed) ? null : parsed;
  }

  // ── Scan flow ────────────────────────────────────────────────────────
  function triggerFileInput() {
    fileInputRef.current?.click();
  }

  async function handleFileSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    setScanPhase("scanning");
    setScanError("");
    setExtracted(null);

    try {
      const data = await extractInvoiceData(file);
      applyExtractedData(data);
      setScanPhase("success");
    } catch (err) {
      setScanPhase("error");
      setScanError(err instanceof Error ? err.message : t("scanError"));
    }

    // Reset the file input so the same file can be chosen again
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  /** Populate the form from extracted data. */
  function applyExtractedData(data: ExtractedInvoice) {
    setExtracted(data);

    // ── Supplier ──
    // Try to match the extracted supplier name to existing suppliers
    const supplierMatch = suppliers.find(
      (s) => s.name.trim() === data.header.supplierName.trim(),
    );
    setSupplierId(supplierMatch?.id ?? 0);

    // ── Line items ──
    const newLines: PurchaseLine[] = data.lineItems.map((item) => {
      // Try to match the raw name to a real product
      const matchedName = matchProductName(item.rawName);
      const product = matchedName
        ? products.find((p) => p.name === matchedName)
        : undefined;

      const isZeroAmount = item.unitPrice === 0 || item.lineTotal === 0;
      const isUnmatched = !product;

      return {
        key: nextLineKey++,
        productId: product?.id ?? 0,
        quantity: item.quantity,
        unitCost: item.unitPrice,
        sellingPrice: product ? Number(product.sale_price) : item.unitPrice,
        expiryDate: "",
        rawName: item.rawName,
        isZeroAmount,
        isUnmatched,
      };
    });

    setLines(newLines.length > 0 ? newLines : [
      {
        key: nextLineKey++,
        productId: 0,
        quantity: 1,
        unitCost: 0,
        sellingPrice: null,
        expiryDate: "",
      },
    ]);
  }

  /** Retry scan after an error. */
  function retryScan() {
    setScanPhase("idle");
    // Re-trigger the file dialog
    triggerFileInput();
  }

  /** Fall back to manual entry — dismiss the scan flow entirely. */
  function dismissScan() {
    setScanPhase("idle");
    setScanError("");
    setExtracted(null);
  }

  async function submitPurchase(
    dualPricing?: { confirmed: true; newSalePrices: Record<number, number> },
  ) {
    if (!validLines.length) return;
    if (paymentExceedsTotal || hasIncompleteCheckLine) return;
    setStatus("submitting");
    setMessage("");
    try {
      const purchase = await createPurchase({
        supplier_id: supplierId > 0 ? supplierId : undefined,
        items: validLines.map((line) => ({
          product_id: line.productId,
          quantity: line.quantity,
          unit_cost: effectiveCost(line),
          ...(line.sellingPrice !== null && line.sellingPrice !== undefined
            ? { selling_price: line.sellingPrice }
            : {}),
          ...(line.expiryDate ? { expiry_date: line.expiryDate } : {}),
          ...(line.isConsignment ? { is_consignment: true } : {}),
        })),
        payment_lines: paymentLines
          .filter((line) => line.amount > 0)
          .map((line) => ({
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
        ...(dualPricing
          ? {
              confirm_dual_pricing: true,
              dual_pricing_new_sale_prices: dualPricing.newSalePrices,
            }
          : {}),
      });
      setStatus("success");
      setMessage(
        `${t("purchaseSuccess")} ${t("invoice")}: ${purchase.invoice_number}`,
      );
      setLines([
        {
          key: nextLineKey++,
          productId: 0,
          quantity: 1,
          unitCost: 0,
          sellingPrice: null,
          expiryDate: "",
        },
      ]);
      setPaymentLines([]);
      // Reset scan state after successful submission
      setScanPhase("idle");
      setExtracted(null);
      setDualPriceProducts(null);
    } catch (error) {
      if (
        error instanceof ApiError &&
        error.code === "dual_price_required" &&
        error.products
      ) {
        // Surface the confirmation modal instead of a plain error banner.
        setDualPriceProducts(error.products);
        setStatus("idle");
        setMessage("");
        return;
      }
      setStatus("error");
      setMessage(error instanceof Error ? error.message : t("apiError"));
    }
  }

  if (viewingPurchaseId !== null) {
    return <PurchaseDetailView purchaseId={viewingPurchaseId} onBack={() => setViewingPurchaseId(null)} />;
  }

  return (
    <main className="main-content purchase-viewport">
      {/* Header - pinned at top */}
      <header className="page-header purchase-header">
        <div>
          <p className="eyebrow">{t("purchases")}</p>
          <h1>{t("purchaseTitle")}</h1>
          <p>{t("purchaseSubtitle")}</p>
        </div>
      </header>

      <div className="tabs" role="tablist">
        <button
          className={`tab ${tab === "entry" ? "active" : ""}`}
          role="tab"
          aria-selected={tab === "entry"}
          onClick={() => setTab("entry")}
        >
          <ShoppingBag size={16} /> {t("newPurchaseTab")}
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
        <PurchasesHistoryTab onSelect={setViewingPurchaseId} />
      ) : (
      <>
      {/* ── Scan Invoice Area ─────────────────────────────────────────────── */}
      <div className={`scan-area ${scanPhase !== "idle" ? "scan-active" : ""}`}>
        <div className="scan-area-header">
          <div className="scan-area-header-text">
            <span className="scan-area-icon">
              <FileText size={17} />
            </span>
            <div>
              <strong style={{ color: "var(--orange-dark)", fontSize: 14 }}>{t("scanInvoice")}</strong>
              <p>{t("scanInfo")}</p>
            </div>
          </div>
          <div className="scan-actions">
            {scanPhase === "idle" && (
              <>
                <button className="scan-button" onClick={triggerFileInput}>
                  <Upload size={17} />
                  {t("uploadPhoto")}
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  className="scan-file-input"
                  onChange={handleFileSelected}
                />
              </>
            )}
          </div>
        </div>

        {/* ── Loading ── */}
        {scanPhase === "scanning" && (
          <div className="scan-loading-overlay">
            <div className="scan-loading-spinner" />
            <span className="scan-loading-text">{t("scanningInvoice")}</span>
          </div>
        )}

        {/* ── Error ── */}
        {scanPhase === "error" && (
          <div className="scan-error-state">
            <div className="scan-error-icon">
              <XCircle size={26} />
            </div>
            <strong style={{ color: "var(--danger)" }}>{t("scanError")}</strong>
            <p>{scanError || t("scanErrorDescription")}</p>
            <div className="scan-error-actions">
              <button className="primary-button" onClick={retryScan}>
                <Camera size={17} />
                {t("scanRetry")}
              </button>
              <button className="secondary-button" onClick={dismissScan}>
                {t("scanFallback")}
              </button>
            </div>
          </div>
        )}

        {/* ── Extracted Invoice Review Panel ── */}
        {scanPhase === "success" && extracted && (
          <div className="scan-review-panel">
            <div className="scan-review-header">
              <h3>
                <CheckCircle2 size={18} color="var(--success)" />
                {t("extractedInvoice")}
                <span className="scan-badge">{t("scanSuccess")}</span>
              </h3>
              <button className="secondary-button" onClick={dismissScan} style={{ fontSize: 12, padding: "6px 12px" }}>
                {t("scanClose")}
              </button>
            </div>
            <div className="scan-review-grid">
              <div className="scan-review-field">
                <label>{t("invoiceNumber")}</label>
                <span>{extracted.header.invoiceNumber}</span>
              </div>
              <div className="scan-review-field">
                <label>{t("invoiceDate")}</label>
                <span>{extracted.header.date}</span>
              </div>
              <div className="scan-review-field">
                <label>{t("invoiceSupplierName")}</label>
                <span>{extracted.header.supplierName}</span>
              </div>
              <div className="scan-review-field">
                <label>{t("paymentTerms")}</label>
                <span>{extracted.header.paymentTerms}</span>
              </div>
            </div>

            {/* Totals summary */}
            <div className="scan-summary-row">
              <div className="scan-summary-item">
                <span>{t("netAmount")}</span>
                <strong>{money(extracted.netAmount)}</strong>
              </div>
              <div className="scan-summary-item">
                <span>{t("vatTotal")}</span>
                <strong>{money(extracted.vatTotal)}</strong>
              </div>
              <div className="scan-summary-item">
                <span>{t("discountTotal")}</span>
                <strong>{money(extracted.discountTotal)}</strong>
              </div>
              <div className={`scan-summary-item ${hasTotalMismatch ? "mismatch" : ""}`}>
                <span>{t("finalTotal")}</span>
                <strong>{money(extracted.finalTotal)}</strong>
              </div>
              <div className={`scan-summary-item ${hasTotalMismatch ? "mismatch" : ""}`}>
                <span>{t("calculatedTotal")}</span>
                <strong>{money(total)}</strong>
              </div>
            </div>
          </div>
        )}

        {/* ── Total mismatch warning banner ── */}
        {hasTotalMismatch && (
          <div className="total-mismatch-banner">
            <AlertTriangle size={20} />
            <div>
              <strong>{t("totalMismatchWarning")}</strong>
              <br />
              <span>
                {t("finalTotal")}: {extracted ? money(extracted.finalTotal) : ""}
                {" — "}
                {t("calculatedTotal")}: {money(total)}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Supplier selector - pinned below header */}
      <div className="purchase-supplier-bar">
        <div className="field" style={{ margin: 0 }}>
          <label>{t("supplier")}</label>
          <select
            value={supplierId}
            onChange={(event) => setSupplierId(parseNumeric(event.target.value))}
          >
            <option value={0}>{t("chooseSupplier")}</option>
            {suppliers.map((supplier) => (
              <option value={supplier.id} key={supplier.id}>
                {supplier.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Scrollable table rows */}
      <section className="panel purchase-form">
        <div className="purchase-section-heading">
          <span>
            <ClipboardList size={16} />
            {t("invoiceItems")}
          </span>
          <div className="add-line-group">
            <input
              type="text"
              inputMode="numeric"
              className="bulk-count-input"
              value={bulkCount}
              onChange={(e) => handleBulkCountChange(e.target.value)}
              onBlur={handleBulkCountBlur}
              aria-label="Number of rows to add"
            />
            <button
              type="button"
              className="secondary-button"
              onClick={addBulkRows}
            >
              <Plus size={18} />
              {t("addLine")}
            </button>
          </div>
        </div>
        <div className="purchase-table">
          <div className="purchase-row purchase-head">
            <span>{t("product")}</span>
            <span>{t("quantity")}</span>
            <span>{t("unitCost")}</span>
            <span>{t("sellingPrice")}</span>
            <span>{t("expiryDate")}</span>
            <span>{t("consignmentShort")}</span>
            <span>{t("total")}</span>
            <span />
          </div>
          <div className="purchase-table-scroll">
            {lines.map((line) => {
              const rowClasses = [
                "purchase-row",
                "animated-line",
                line.isZeroAmount ? "warning-zero-amount" : "",
                line.isUnmatched ? "warning-unmatched" : "",
              ]
                .filter(Boolean)
                .join(" ");

              return (
                <div className={rowClasses} key={line.key}>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <ProductCombobox
                      value={line.productId}
                      products={products}
                      onChange={(productId) => selectProduct(line, productId)}
                      onProductCreated={(product) => selectNewlyCreatedProduct(line, product)}
                    />
                    {/* Warning chips */}
                    {(line.isZeroAmount || line.isUnmatched) && (
                      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                        {line.isZeroAmount && (
                          <span className="warning-chip zero-amount">
                            <AlertTriangle size={13} />
                            {t("zeroAmountWarning")}
                          </span>
                        )}
                        {line.isUnmatched && (
                          <span className="warning-chip unmatched">
                            <Info size={13} />
                            {t("unmatchedProductWarning")}
                          </span>
                        )}
                      </div>
                    )}
                    {/* Raw name display + actions for unmatched */}
                    {line.rawName && (
                      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                        <span style={{ fontSize: 11, color: "var(--muted)", fontStyle: "italic" }}>
                          {line.rawName}
                        </span>
                        {line.isUnmatched && (
                          <span className="unmatched-actions">
                            <button
                              onClick={() => {
                                // Keep as free text: clear unmatched flag, keep productId=0
                                updateLine(line.key, { isUnmatched: false });
                              }}
                              title={t("keepAsText")}
                            >
                              {t("keepAsText")}
                            </button>
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                  <input
                    type="number"
                    min="0.001"
                    step="0.001"
                    value={line.quantity}
                    onChange={(event) =>
                      updateLine(line.key, { quantity: parseNumeric(event.target.value) })
                    }
                  />
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={line.isPromotional ? 0 : line.unitCost}
                      disabled={line.isPromotional}
                      placeholder={line.isPromotional ? t("promotionalFree") : undefined}
                      onChange={(event) =>
                        updateLine(line.key, { unitCost: parseNumeric(event.target.value) })
                      }
                    />
                    <label className="promotional-checkbox" title={t("promotionalHint")}>
                      <input
                        type="checkbox"
                        checked={line.isPromotional ?? false}
                        onChange={(event) =>
                          updateLine(line.key, { isPromotional: event.target.checked })
                        }
                      />
                      {t("promotionalItem")}
                    </label>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={line.sellingPrice ?? ""}
                      onChange={(event) =>
                        updateLine(line.key, {
                          sellingPrice: parseOptionalNumber(event.target.value),
                        })
                      }
                    />
                    {(() => {
                      const profit = computeLineProfit(line);
                      if (!profit) return <small className="line-profit-hint muted-text">—</small>;
                      return (
                        <small className={`line-profit-hint margin-value ${getMarginStatus(profit.marginPct)}`}>
                          {money(profit.profitPerUnit)} ({formatMarginPct(profit.marginPct, language, number)})
                          {profit.isPromotional && <span className="promotional-badge">{t("promotionalBadge")}</span>}
                        </small>
                      );
                    })()}
                  </div>
                  <JalaliDatePicker
                    value={line.expiryDate ?? ""}
                    onChange={(isoDate) =>
                      updateLine(line.key, { expiryDate: isoDate })
                    }
                  />
                  <label className="consignment-checkbox" title={t("consignmentHint")}>
                    <input
                      type="checkbox"
                      checked={line.isConsignment ?? false}
                      onChange={(event) =>
                        updateLine(line.key, { isConsignment: event.target.checked })
                      }
                    />
                    {t("consignmentShort")}
                  </label>
                  <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <strong>{money(line.quantity * effectiveCost(line))}</strong>
                    {(() => {
                      const profit = computeLineProfit(line);
                      if (!profit) return null;
                      return (
                        <small className={`line-profit-hint margin-value ${getMarginStatus(profit.marginPct)}`}>
                          {t("lineProfitAbbrev")} {money(profit.lineProfitTotal)}
                          {profit.isPromotional && <span className="promotional-badge">{t("promotionalBadge")}</span>}
                        </small>
                      );
                    })()}
                  </div>
                  <button
                    className="icon-button danger"
                    disabled={lines.length === 1}
                    onClick={() =>
                      setLines((current) =>
                        current.filter((item) => item.key !== line.key),
                      )
                    }
                    aria-label={t("remove")}
                  >
                    <Trash2 size={17} />
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        {/* Payment breakdown — split across cash/card/check lines */}
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
                <option value="card">{t("bankTransfer")}</option>
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

          {paymentExceedsTotal && <div className="feedback-banner error">{t("paymentExceedsTotal")}</div>}
          {hasIncompleteCheckLine && !paymentExceedsTotal && (
            <div className="feedback-banner error">{t("checkLineIncomplete")}</div>
          )}
        </div>

        {/* Summary + Submit - pinned at bottom */}
        <div className="purchase-summary">
          <div className="purchase-summary-info">
            <div className="purchase-summary-count">
              <PackagePlus size={22} />
              <span>{validLines.length} {t("items")}</span>
            </div>
            {consignmentValue > 0 && (
              <div className="total-row muted-text">
                <span>{t("consignmentValue")}</span>
                <strong>{money(consignmentValue)}</strong>
              </div>
            )}
            <div className="total-row">
              <span>{consignmentValue > 0 ? t("payableTotal") : t("total")}</span>
              <strong>{money(payableTotal)}</strong>
            </div>
            {invoiceProfitSummary && (
              <div className="total-row">
                <span>{t("totalInvoiceProfit")}</span>
                <strong
                  className={
                    invoiceProfitSummary.blendedMarginPct === null
                      ? undefined
                      : `margin-value ${getMarginStatus(invoiceProfitSummary.blendedMarginPct)}`
                  }
                >
                  {money(invoiceProfitSummary.totalProfit)}
                  {invoiceProfitSummary.blendedMarginPct !== null &&
                    ` (${formatMarginPct(invoiceProfitSummary.blendedMarginPct, language, number)})`}
                </strong>
              </div>
            )}
            <label className="consignment-whole-invoice" title={t("consignmentHint")}>
              <input
                type="checkbox"
                checked={allLinesConsignment}
                onChange={(event) => toggleAllConsignment(event.target.checked)}
              />
              {t("consignmentWholeInvoice")}
            </label>
          </div>
          <button
            className={`primary-button submit-button ${status === "submitting" ? "is-loading" : ""}`}
            disabled={!validLines.length || status === "submitting" || paymentExceedsTotal || hasIncompleteCheckLine}
            onClick={() => submitPurchase()}
          >
            <CheckCircle2 size={18} />
            {status === "submitting" ? t("loading") : t("submitPurchase")}
          </button>
        </div>
      </section>

      {dualPriceProducts && (
        <DualPriceConfirmModal
          products={dualPriceProducts}
          submitting={status === "submitting"}
          onConfirm={(newSalePrices) =>
            submitPurchase({ confirmed: true, newSalePrices })
          }
          onSkip={() => submitPurchase({ confirmed: true, newSalePrices: {} })}
          onCancel={() => setDualPriceProducts(null)}
        />
      )}
      </>
      )}
    </main>
  );
}
