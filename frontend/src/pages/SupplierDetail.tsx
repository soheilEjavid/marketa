import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, DollarSign } from "lucide-react";

import { getSupplierLedger } from "../api";
import { useI18n } from "../i18n";
import type { SupplierLedger } from "../types";

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
            </article>
          </section>

          <section className="panel ledger-table">
            <div className="inventory-row inventory-head">
              <span>{t("date")}</span>
              <span>{t("reference")}</span>
              <span>{t("type")}</span>
              <span>{t("debit")}</span>
              <span>{t("credit")}</span>
              <span>{t("balance")}</span>
            </div>
            {ledger.entries.map((entry) => (
              <div className="inventory-row animated-line" key={entry.id}>
                <time>
                  {new Intl.DateTimeFormat(locale, {
                    dateStyle: "medium",
                    timeStyle: "short",
                  }).format(new Date(entry.occurred_at))}
                </time>
                <span>{entry.reference}</span>
                <span className={`type-pill ${entry.entry_type}`}>
                  {t(entry.entry_type === "purchase" ? "purchase" : "payment")}
                </span>
                <strong className="quantity-positive">{Number(entry.debit) > 0 ? money(Number(entry.debit)) : "—"}</strong>
                <strong className="quantity-negative">{Number(entry.credit) > 0 ? money(Number(entry.credit)) : "—"}</strong>
                <strong>{money(Number(entry.running_balance))}</strong>
              </div>
            ))}
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