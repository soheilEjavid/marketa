import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";

import { getAuditLogs, getPurchasesPage, getSuppliers } from "../api";
import { useI18n } from "../i18n";
import type { Purchase } from "../types";
import { dateToJalaliStr, isoToJalaliStr } from "../utils/jalali";

type PurchasesHistoryTabProps = {
  onSelect: (purchaseId: number) => void;
};

const PAGE_SIZE = 20;

/**
 * A compact payment summary for the history row — e.g. "نقد + ۲ چک". Check
 * due dates are individually listed in the hover title rather than
 * collapsed into one, since a purchase can carry several checks due on
 * different dates.
 */
function paymentSummary(
  purchase: Purchase,
  t: (key: string) => string,
  number: (value: number) => string,
): { label: string; title?: string } {
  if (!purchase.payment_lines.length) {
    return { label: t("noPaymentRecorded") };
  }
  const checks = purchase.payment_lines.filter((line) => line.method === "check");
  const others = purchase.payment_lines.filter((line) => line.method !== "check");

  const parts: string[] = [];
  const otherMethods = Array.from(new Set(others.map((line) => t(line.method))));
  if (otherMethods.length) parts.push(otherMethods.join(" + "));

  if (checks.length === 1) {
    const due = checks[0].check_due_date ? isoToJalaliStr(checks[0].check_due_date) : "—";
    parts.push(`${t("check")} (${due})`);
  } else if (checks.length > 1) {
    parts.push(`${number(checks.length)} ${t("check")}`);
  }

  const title =
    checks.length > 1
      ? checks.map((line) => (line.check_due_date ? isoToJalaliStr(line.check_due_date) : "—")).join("، ")
      : undefined;

  return { label: parts.join(" + "), title };
}

export function PurchasesHistoryTab({ onSelect }: PurchasesHistoryTabProps) {
  const { t, money, number } = useI18n();
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<"date_desc" | "date_asc">("date_desc");
  const [page, setPage] = useState(0);
  const [purchases, setPurchases] = useState<Purchase[]>([]);
  const [total, setTotal] = useState(0);
  const [editedIds, setEditedIds] = useState<Set<number>>(new Set());
  const [supplierNames, setSupplierNames] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getSuppliers()
      .then((suppliers) => setSupplierNames(Object.fromEntries(suppliers.map((s) => [s.id, s.name]))))
      .catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    const timeout = window.setTimeout(() => {
      getPurchasesPage({ search, sort, offset: page * PAGE_SIZE, limit: PAGE_SIZE })
        .then((result) => {
          setPurchases(result.items);
          setTotal(result.total);
          getAuditLogs({ entityType: "purchase", action: "edit", limit: 500 })
            .then((logs) => setEditedIds(new Set(logs.map((entry) => entry.entity_id).filter((id): id is number => id !== null))))
            .catch(() => {});
        })
        .catch(() => {})
        .finally(() => setLoading(false));
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [search, sort, page]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div>
      <div className="product-filters">
        <label className="search-field">
          <Search size={18} />
          <input
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(0);
            }}
            placeholder={t("searchInvoices")}
          />
        </label>
        <select
          value={sort}
          onChange={(event) => {
            setSort(event.target.value as "date_desc" | "date_asc");
            setPage(0);
          }}
        >
          <option value="date_desc">{t("newestFirst")}</option>
          <option value="date_asc">{t("oldestFirst")}</option>
        </select>
      </div>

      <div className="panel" style={{ padding: 0, overflow: "hidden" }}>
        <div className="inventory-table">
          <div className="inventory-row inventory-head invoice-history-columns-purchase">
            <span>{t("invoice")}</span>
            <span>{t("date")}</span>
            <span>{t("supplier")}</span>
            <span>{t("paymentBreakdown")}</span>
            <span>{t("total")}</span>
            <span />
          </div>

          {loading ? (
            <div className="empty-state compact">{t("loading")}</div>
          ) : purchases.length === 0 ? (
            <div className="empty-state compact">{t("noSearchResults")}</div>
          ) : (
            purchases.map((purchase) => {
              const payment = paymentSummary(purchase, t, number);
              return (
                <button
                  type="button"
                  className="inventory-row invoice-history-columns-purchase animated-line invoice-history-row"
                  key={purchase.id}
                  onClick={() => onSelect(purchase.id)}
                >
                  <span>
                    {purchase.invoice_number}
                    {editedIds.has(purchase.id) && <span className="edited-badge inline">{t("editedBadge")}</span>}
                  </span>
                  <span>{dateToJalaliStr(new Date(purchase.created_at))}</span>
                  <span>{purchase.supplier_id ? supplierNames[purchase.supplier_id] ?? "—" : "—"}</span>
                  <span className="payment-summary-chip" title={payment.title}>
                    {payment.label}
                  </span>
                  <strong>{money(Number(purchase.total))}</strong>
                  <span className="text-button">{t("viewDetails")} <ChevronLeft size={14} /></span>
                </button>
              );
            })
          )}
        </div>
      </div>

      {totalPages > 1 && (
        <div className="pagination-controls">
          <button className="icon-button" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>
            <ChevronRight size={16} />
          </button>
          <span>{number(page + 1)} / {number(totalPages)}</span>
          <button
            className="icon-button"
            disabled={page >= totalPages - 1}
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
          >
            <ChevronLeft size={16} />
          </button>
        </div>
      )}
    </div>
  );
}
