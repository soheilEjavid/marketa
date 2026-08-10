import { useEffect, useState } from "react";
import { ArrowLeft, History, Pencil, Printer } from "lucide-react";

import { getAuditLogs, getCustomers, getProducts, getSale } from "../api";
import { useI18n } from "../i18n";
import { calculateInvoiceMargin, calculateMarginPct, formatMarginPct, getMarginStatus } from "../lib/margin";
import { formatQuantityWithUnit } from "../lib/quantity";
import { canEditSale } from "../permissions";
import { getSession } from "../session";
import type { AuditLogEntry, Sale } from "../types";
import { dateToJalaliStr } from "../utils/jalali";
import { SaleEditForm } from "./SaleEditForm";

type SaleDetailViewProps = {
  saleId: number;
  onBack: () => void;
};

function formatDateTime(iso: string, locale: string): string {
  const date = new Date(iso);
  return `${dateToJalaliStr(date)} ${date.toLocaleTimeString(locale === "fa-IR" ? undefined : locale, {
    hour: "2-digit",
    minute: "2-digit",
  })}`;
}

export function SaleDetailView({ saleId, onBack }: SaleDetailViewProps) {
  const { t, money, number, locale, language } = useI18n();
  const [sale, setSale] = useState<Sale | null>(null);
  const [customerName, setCustomerName] = useState<string | null>(null);
  const [productNames, setProductNames] = useState<Record<number, string>>({});
  // Weighted lines need their unit and precision to render as a
  // measurement; SaleItemRead carries neither, so both come from the
  // product list this view already fetches for the names.
  const [productUnits, setProductUnits] = useState<
    Record<number, { isWeighted: boolean; unit: string | null }>
  >({});
  const [history, setHistory] = useState<AuditLogEntry[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  function load() {
    setLoading(true);
    setError("");
    Promise.all([
      getSale(saleId),
      getAuditLogs({ entityType: "sale", entityId: saleId, action: "edit" }),
      getProducts(),
    ])
      .then(([saleData, logs, products]) => {
        setSale(saleData);
        setHistory(logs);
        setProductNames(Object.fromEntries(products.map((p) => [p.id, p.name])));
        setProductUnits(
          Object.fromEntries(
            products.map((p) => [p.id, { isWeighted: p.is_weighted, unit: p.unit }]),
          ),
        );
        if (saleData.customer_id) {
          getCustomers()
            .then((customers) => {
              const match = customers.find((c) => c.id === saleData.customer_id);
              setCustomerName(match?.full_name ?? null);
            })
            .catch(() => setCustomerName(null));
        } else {
          setCustomerName(null);
        }
      })
      .catch(() => setError(t("apiError")))
      .finally(() => setLoading(false));
  }

  useEffect(load, [saleId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) {
    return (
      <main className="main-content">
        <div className="empty-state">{t("loading")}</div>
      </main>
    );
  }

  if (error || !sale) {
    return (
      <main className="main-content">
        <div className="feedback-banner error">{error || t("apiError")}</div>
        <button className="secondary-button" onClick={onBack}>
          <ArrowLeft size={16} /> {t("back")}
        </button>
      </main>
    );
  }

  // Any sale can now have a remaining balance (a split cash/card payment
  // can leave part on account without the sale being classified "credit"),
  // so this no longer gates on payment_method at all.
  const isPartial = Number(sale.remaining_amount) > 0;
  const wasEdited = history.length > 0;
  const invoiceMargin = calculateInvoiceMargin(sale.items);
  const canEdit = canEditSale(getSession()?.role ?? "");

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
            <span>{t("receiptTitle")}</span>
            {wasEdited && <span className="edited-badge">{t("editedBadge")}</span>}
          </div>

          <div className="receipt-meta">
            <span>{t("invoice")}: {sale.invoice_number}</span>
            <span>{formatDateTime(sale.created_at, locale)}</span>
          </div>

          <table className="receipt-table">
            <thead>
              <tr>
                <th>{t("product")}</th>
                <th>{t("quantity")}</th>
                <th>{t("unitPrice")}</th>
                <th>{t("itemDiscount")}</th>
                <th>{t("costBasis")}</th>
                <th>{t("marginPct")}</th>
                <th>{t("lineTotal")}</th>
              </tr>
            </thead>
            <tbody>
              {sale.items.map((item) => {
                const marginPct = calculateMarginPct(Number(item.unit_price), Number(item.cost_price));
                return (
                  <tr key={item.id}>
                    <td>
                      {productNames[item.product_id] ?? `#${item.product_id}`}
                      {item.price_tier && (
                        <small className="receipt-tier-note">
                          {" "}
                          ({item.price_tier === "old" ? t("dualPriceOldPrice") : t("dualPriceNewPrice")})
                        </small>
                      )}
                    </td>
                    <td>
                      {formatQuantityWithUnit(
                        Number(item.quantity),
                        productUnits[item.product_id]?.isWeighted ?? false,
                        productUnits[item.product_id]?.isWeighted
                          ? productUnits[item.product_id]?.unit
                          : null,
                        locale,
                        number,
                      )}
                    </td>
                    <td>{money(Number(item.unit_price))}</td>
                    <td>{Number(item.discount) > 0 ? money(Number(item.discount)) : "—"}</td>
                    <td className="muted-text">{money(Number(item.cost_price))}</td>
                    <td>
                      {marginPct === null ? (
                        "—"
                      ) : (
                        <span className={`margin-value ${getMarginStatus(marginPct)}`}>
                          {formatMarginPct(marginPct, language, number)}
                        </span>
                      )}
                    </td>
                    <td>{money(Number(item.line_total))}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          <div className="receipt-summary">
            <div>
              <span>{t("subtotal")}</span>
              <strong>{money(Number(sale.subtotal))}</strong>
            </div>
            {Number(sale.discount) > 0 && (
              <div>
                <span>{t("discount")}</span>
                <strong>-{money(Number(sale.discount))}</strong>
              </div>
            )}
            <div className="receipt-total-row">
              <span>{t("total")}</span>
              <strong>{money(Number(sale.total))}</strong>
            </div>
            <div>
              <span>{t("invoiceMargin")}</span>
              <strong>
                {invoiceMargin.marginPct === null ? (
                  "—"
                ) : (
                  <span className={`margin-value ${getMarginStatus(invoiceMargin.marginPct)}`}>
                    {formatMarginPct(invoiceMargin.marginPct, language, number)}
                  </span>
                )}
              </strong>
            </div>
            <div>
              <span>{t("paymentMethod")}</span>
              <strong>{t(sale.payment_method)}</strong>
            </div>
            {customerName && (
              <div>
                <span>{t("customer")}</span>
                <strong>{customerName}</strong>
              </div>
            )}
            {isPartial && (
              <>
                <div>
                  <span>{t("paidAmount")}</span>
                  <strong>{money(Number(sale.paid_amount))}</strong>
                </div>
                <div>
                  <span>{t("remainingBalance")}</span>
                  <strong>{money(Number(sale.remaining_amount))}</strong>
                </div>
              </>
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
        <SaleEditForm
          sale={sale}
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
