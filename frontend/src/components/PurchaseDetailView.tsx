import { useEffect, useState } from "react";
import { ArrowLeft, History, Pencil, Printer } from "lucide-react";

import { getAuditLogs, getProducts, getPurchase, getSuppliers } from "../api";
import { useI18n } from "../i18n";
import { canManagePurchases } from "../permissions";
import { getSession } from "../session";
import type { AuditLogEntry, Purchase } from "../types";
import { dateToJalaliStr, isoToJalaliStr } from "../utils/jalali";
import { PurchaseEditForm } from "./PurchaseEditForm";

type PurchaseDetailViewProps = {
  purchaseId: number;
  onBack: () => void;
};

function formatDateTime(iso: string, locale: string): string {
  const date = new Date(iso);
  return `${dateToJalaliStr(date)} ${date.toLocaleTimeString(locale === "fa-IR" ? undefined : locale, {
    hour: "2-digit",
    minute: "2-digit",
  })}`;
}

export function PurchaseDetailView({ purchaseId, onBack }: PurchaseDetailViewProps) {
  const { t, money, number, locale } = useI18n();
  const [purchase, setPurchase] = useState<Purchase | null>(null);
  const [supplierName, setSupplierName] = useState<string | null>(null);
  const [productNames, setProductNames] = useState<Record<number, string>>({});
  const [history, setHistory] = useState<AuditLogEntry[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  function load() {
    setLoading(true);
    setError("");
    Promise.all([
      getPurchase(purchaseId),
      getAuditLogs({ entityType: "purchase", entityId: purchaseId, action: "edit" }),
      getProducts(),
    ])
      .then(([purchaseData, logs, products]) => {
        setPurchase(purchaseData);
        setHistory(logs);
        setProductNames(Object.fromEntries(products.map((p) => [p.id, p.name])));
        if (purchaseData.supplier_id) {
          getSuppliers()
            .then((suppliers) => {
              const match = suppliers.find((s) => s.id === purchaseData.supplier_id);
              setSupplierName(match?.name ?? null);
            })
            .catch(() => setSupplierName(null));
        } else {
          setSupplierName(null);
        }
      })
      .catch(() => setError(t("apiError")))
      .finally(() => setLoading(false));
  }

  useEffect(load, [purchaseId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) {
    return (
      <main className="main-content">
        <div className="empty-state">{t("loading")}</div>
      </main>
    );
  }

  if (error || !purchase) {
    return (
      <main className="main-content">
        <div className="feedback-banner error">{error || t("apiError")}</div>
        <button className="secondary-button" onClick={onBack}>
          <ArrowLeft size={16} /> {t("back")}
        </button>
      </main>
    );
  }

  const isPartial = Number(purchase.remaining_amount) > 0;
  const wasEdited = history.length > 0;
  const canEdit = canManagePurchases(getSession()?.role ?? "");

  return (
    <main className="main-content">
      <div className="receipt-page">
        <div className="receipt-actions no-print">
          <button className="secondary-button" onClick={onBack}>
            <ArrowLeft size={16} /> {t("back")}
          </button>
          {canEdit && (
            <button className="secondary-button" onClick={() => setShowEdit(true)}>
              <Pencil size={16} /> {t("editInvoice")}
            </button>
          )}
          <button className="primary-button" onClick={() => window.print()}>
            <Printer size={16} /> {t("printReceipt")}
          </button>
        </div>

        <div id="receipt-print-area" className="receipt-sheet">
          <div className="receipt-header">
            <strong>{t("localStore")}</strong>
            <span>{t("purchaseTitle")}</span>
            {wasEdited && <span className="edited-badge">{t("editedBadge")}</span>}
          </div>

          <div className="receipt-meta">
            <span>{t("invoice")}: {purchase.invoice_number}</span>
            <span>{formatDateTime(purchase.created_at, locale)}</span>
          </div>

          <table className="receipt-table">
            <thead>
              <tr>
                <th>{t("product")}</th>
                <th>{t("quantity")}</th>
                <th>{t("unitCost")}</th>
                <th>{t("sellingPrice")}</th>
                <th>{t("lineTotal")}</th>
              </tr>
            </thead>
            <tbody>
              {purchase.items.map((item) => (
                <tr key={item.id}>
                  <td>{productNames[item.product_id] ?? `#${item.product_id}`}</td>
                  <td>{number(Number(item.quantity))}</td>
                  <td>{money(Number(item.unit_cost))}</td>
                  <td>{item.selling_price ? money(Number(item.selling_price)) : "—"}</td>
                  <td>{money(Number(item.line_total))}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="receipt-summary">
            <div className="receipt-total-row">
              <span>{t("total")}</span>
              <strong>{money(Number(purchase.total))}</strong>
            </div>
            {supplierName && (
              <div>
                <span>{t("supplier")}</span>
                <strong>{supplierName}</strong>
              </div>
            )}
            {purchase.payment_lines.length > 0 && (
              <div className="payment-breakdown">
                <span className="payment-breakdown-title">{t("paymentBreakdown")}</span>
                {purchase.payment_lines.map((line) => (
                  <div className="payment-breakdown-row" key={line.id}>
                    <span>{t(line.method)}</span>
                    <strong>{money(Number(line.amount))}</strong>
                    {line.method === "check" && (
                      <span className="payment-breakdown-check-meta">
                        {line.check_number && `${t("checkNumber")}: ${line.check_number}`}
                        {line.check_bank_name && ` · ${line.check_bank_name}`}
                        {line.check_due_date && ` · ${t("checkDueDate")}: ${isoToJalaliStr(line.check_due_date)}`}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
            {purchase.payment_lines.length === 0 && Number(purchase.remaining_amount) > 0 && (
              <div className="payment-breakdown-empty">{t("noPaymentRecorded")}</div>
            )}
            {isPartial && (
              <div>
                <span>{t("remainingBalance")}</span>
                <strong>{money(Number(purchase.remaining_amount))}</strong>
              </div>
            )}
          </div>
        </div>

        {wasEdited && (
          <div className="panel no-print">
            <button className="text-button" onClick={() => setShowHistory((current) => !current)}>
              <History size={16} /> {t("editHistory")} ({number(history.length)})
            </button>
            {showHistory && (
              <div className="edit-history-list">
                {history.map((entry) => {
                  let parsed: { reason?: string; old?: { total?: string }; new?: { total?: string } } | null = null;
                  try {
                    parsed = JSON.parse(entry.details ?? "{}");
                  } catch {
                    parsed = null;
                  }
                  return (
                    <div className="edit-history-row" key={entry.id}>
                      <div>
                        <strong>{parsed?.reason || entry.details}</strong>
                        <small>
                          {entry.username || t("devUser")} · {entry.occurred_at ? formatDateTime(entry.occurred_at, locale) : "—"}
                        </small>
                      </div>
                      {parsed?.old?.total && parsed?.new?.total && (
                        <span className="edit-history-delta">
                          {money(Number(parsed.old.total))} → {money(Number(parsed.new.total))}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {showEdit && (
        <PurchaseEditForm
          purchase={purchase}
          onClose={() => setShowEdit(false)}
          onSaved={() => {
            setShowEdit(false);
            load();
          }}
        />
      )}
    </main>
  );
}
