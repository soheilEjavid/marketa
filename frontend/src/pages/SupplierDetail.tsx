import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ArrowLeft, DollarSign } from "lucide-react";

import { createSupplierPayment, getErrorMessage, getSupplierLedger } from "../api";
import { useI18n } from "../i18n";
import type { SupplierLedger } from "../types";
import { PurchaseDetailView } from "../components/PurchaseDetailView";
import { AmountInput } from "../components/AmountInput";

type SupplierDetailProps = {
  supplierId: number;
  supplierName: string;
  onBack: () => void;
};

export function SupplierDetail({ supplierId, supplierName, onBack }: SupplierDetailProps) {
  const { locale, money, t } = useI18n();
  const [ledger, setLedger] = useState<SupplierLedger | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [showPaymentForm, setShowPaymentForm] = useState(false);
  const [paymentAmount, setPaymentAmount] = useState("");
  const [paymentMethod, setPaymentMethod] = useState<"cash" | "card">("card");
  const [paymentSubmitting, setPaymentSubmitting] = useState(false);
  const [paymentError, setPaymentError] = useState("");
  const [paymentSuccess, setPaymentSuccess] = useState(false);
  const [viewingPurchaseId, setViewingPurchaseId] = useState<number | null>(null);

  const loadLedger = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setLedger(await getSupplierLedger(supplierId));
    } catch {
      setError(t("apiError"));
    } finally {
      setLoading(false);
    }
  }, [supplierId, t]);

  useEffect(() => {
    loadLedger();
  }, [loadLedger]);

  async function handlePaymentSubmit(event: FormEvent) {
    event.preventDefault();
    const amount = Number(paymentAmount);
    if (!amount || amount <= 0) return;
    setPaymentError("");
    setPaymentSuccess(false);
    // Immediate client-side check, same rule the backend now enforces
    // (services/financials.py::record_supplier_payment).
    if (ledger && amount > Number(ledger.balance)) {
      setPaymentError(t("paymentExceedsBalance"));
      return;
    }
    setPaymentSubmitting(true);
    try {
      await createSupplierPayment(supplierId, { amount, method: paymentMethod });
      setPaymentAmount("");
      setPaymentSuccess(true);
      await loadLedger();
    } catch (err) {
      setPaymentError(getErrorMessage(err, t));
    } finally {
      setPaymentSubmitting(false);
    }
  }

  if (viewingPurchaseId !== null) {
    return <PurchaseDetailView purchaseId={viewingPurchaseId} onBack={() => setViewingPurchaseId(null)} />;
  }

  return (
    <main className="main-content">
      <header className="page-header">
        <div>
          <p className="eyebrow">{t("suppliers")}</p>
          <h1>{supplierName}</h1>
        </div>
        <div className="topbar-actions">
          <button className="secondary-button" onClick={onBack}>
            <ArrowLeft size={18} /> {t("back")}
          </button>
        </div>
      </header>

      {error && <div className="feedback-banner error">{error}</div>}

      {ledger && (
        <>
          <section className="metric-grid stagger" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
            <article className="metric-card">
              <div className="metric-icon"><DollarSign /></div>
              <p>{t("balance")}</p>
              <strong>{money(Number(ledger.balance))}</strong>
              {Number(ledger.balance) > 0 && (
                <button
                  type="button"
                  className="secondary-button"
                  style={{ marginTop: 8 }}
                  onClick={() => {
                    setShowPaymentForm((current) => !current);
                    setPaymentSuccess(false);
                  }}
                >
                  {t("recordPayment")}
                </button>
              )}
            </article>
          </section>

          {showPaymentForm && (
            <section className="panel" style={{ marginBottom: 16 }}>
              <form className="form-grid" onSubmit={handlePaymentSubmit}>
                {paymentError && <div className="feedback-banner error full-span">{paymentError}</div>}
                {paymentSuccess && (
                  <div className="feedback-banner success full-span">{t("paymentRecordedSuccess")}</div>
                )}
                <label className="field">
                  <span>{t("recordPaymentAmount")}</span>
                  <AmountInput
                    min="0.01"
                    value={Number(paymentAmount) || null}
                    onChange={(v) => setPaymentAmount(v === null ? "" : String(v))}
                    placeholder="0"
                    required
                  />
                </label>
                <label className="field">
                  <span>{t("paymentLinesTitle")}</span>
                  <div className="payment-method-toggle">
                    <button
                      type="button"
                      className={`price-tier-button ${paymentMethod === "cash" ? "price-tier-selected" : ""}`}
                      onClick={() => setPaymentMethod("cash")}
                    >
                      {t("cash")}
                    </button>
                    <button
                      type="button"
                      className={`price-tier-button ${paymentMethod === "card" ? "price-tier-selected" : ""}`}
                      onClick={() => setPaymentMethod("card")}
                    >
                      {t("card")}
                    </button>
                  </div>
                </label>
                <div className="form-actions full-span">
                  <button className="primary-button" type="submit" disabled={paymentSubmitting}>
                    {paymentSubmitting ? t("loading") : t("recordPayment")}
                  </button>
                </div>
              </form>
            </section>
          )}

          <section className="panel ledger-table">
            <div className="inventory-row inventory-head">
              <span>{t("date")}</span>
              <span>{t("reference")}</span>
              <span>{t("type")}</span>
              <span>{t("debit")}</span>
              <span>{t("credit")}</span>
              <span>{t("balance")}</span>
            </div>
            {ledger.entries.map((entry) => {
              // Purchase rows drill into the full invoice (PurchaseDetailView)
              // — entry.id is "purchase-{numeric id}" from the backend
              // (services/financials.py::supplier_ledger).
              const isPurchase = entry.entry_type === "purchase";
              const RowTag = isPurchase ? "button" : "div";
              return (
              <RowTag
                type={isPurchase ? "button" : undefined}
                className={`inventory-row animated-line ${isPurchase ? "invoice-history-row" : ""}`}
                key={entry.id}
                onClick={isPurchase ? () => setViewingPurchaseId(Number(entry.id.replace("purchase-", ""))) : undefined}
              >
                <time>
                  {new Intl.DateTimeFormat(locale, {
                    dateStyle: "medium",
                    timeStyle: "short",
                  }).format(new Date(entry.occurred_at))}
                </time>
                <span>{entry.reference}</span>
                <span className={`type-pill ${entry.entry_type}`}>
                  {t(entry.entry_type === "purchase" ? "purchase" : "payment")}
                  {entry.payment_status && entry.payment_status !== "paid" && (
                    <span className={`credit-status-badge ${entry.payment_status}`}>
                      {t(entry.payment_status === "unpaid" ? "unpaidStatus" : "partialStatus")}
                    </span>
                  )}
                </span>
                <strong className="quantity-positive">{Number(entry.debit) > 0 ? money(Number(entry.debit)) : "—"}</strong>
                <strong className="quantity-negative">{Number(entry.credit) > 0 ? money(Number(entry.credit)) : "—"}</strong>
                <strong>{money(Number(entry.running_balance))}</strong>
              </RowTag>
              );
            })}
            {!loading && ledger.entries.length === 0 && (
              <div className="empty-state">{t("noTransactions")}</div>
            )}
          </section>
        </>
      )}

      {loading && <div className="empty-state">{t("loading")}</div>}
    </main>
  );
}