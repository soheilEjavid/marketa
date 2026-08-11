import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";

import { getAuditLogs, getCustomers, getSalesPage } from "../api";
import { canCancelSale } from "../permissions";
import { getSession } from "../session";
import { useI18n } from "../i18n";
import type { Sale } from "../types";
import { dateToJalaliStr } from "../utils/jalali";

type SalesHistoryTabProps = {
  onSelect: (saleId: number) => void;
};

const PAGE_SIZE = 20;

export function SalesHistoryTab({ onSelect }: SalesHistoryTabProps) {
  const { t, money, number } = useI18n();
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<"date_desc" | "date_asc">("date_desc");
  const [page, setPage] = useState(0);
  const [sales, setSales] = useState<Sale[]>([]);
  const [total, setTotal] = useState(0);
  const [editedIds, setEditedIds] = useState<Set<number>>(new Set());
  const [customerNames, setCustomerNames] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  /** Voided invoices are off by default — most of the time the history is a
   *  list of what was actually sold. A manager can switch them on when
   *  somebody asks what happened to an invoice that is no longer there. */
  const [showCancelled, setShowCancelled] = useState(false);
  const canSeeCancelled = canCancelSale(getSession()?.role ?? "");

  useEffect(() => {
    getCustomers()
      .then((customers) => setCustomerNames(Object.fromEntries(customers.map((c) => [c.id, c.full_name]))))
      .catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    const timeout = window.setTimeout(() => {
      getSalesPage({ search, sort, offset: page * PAGE_SIZE, limit: PAGE_SIZE, includeCancelled: showCancelled })
        .then((result) => {
          setSales(result.items);
          setTotal(result.total);
          getAuditLogs({ entityType: "sale", action: "edit", limit: 500 })
            .then((logs) => setEditedIds(new Set(logs.map((entry) => entry.entity_id).filter((id): id is number => id !== null))))
            .catch(() => {});
        })
        .catch(() => {})
        .finally(() => setLoading(false));
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [search, sort, page, showCancelled]);

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
        {canSeeCancelled && (
          <label className="promotional-checkbox" title={t("showCancelledInvoices")}>
            <input
              type="checkbox"
              checked={showCancelled}
              onChange={(event) => {
                setShowCancelled(event.target.checked);
                setPage(0);
              }}
            />
            {t("showCancelledInvoices")}
          </label>
        )}
      </div>

      <div className="panel" style={{ padding: 0, overflow: "hidden" }}>
        <div className="inventory-table">
          <div className="inventory-row inventory-head invoice-history-columns">
            <span>{t("invoice")}</span>
            <span>{t("date")}</span>
            <span>{t("customer")}</span>
            <span>{t("paymentMethod")}</span>
            <span>{t("total")}</span>
            <span />
          </div>

          {loading ? (
            <div className="empty-state compact">{t("loading")}</div>
          ) : sales.length === 0 ? (
            <div className="empty-state compact">{t("noSearchResults")}</div>
          ) : (
            sales.map((sale) => (
              <button
                type="button"
                className={`inventory-row invoice-history-columns animated-line invoice-history-row ${sale.status === "cancelled" ? "is-cancelled" : ""}`}
                key={sale.id}
                onClick={() => onSelect(sale.id)}
              >
                <span>
                  {sale.invoice_number}
                  {sale.status === "cancelled" && (
                    <span className="cancelled-badge inline">{t("cancelledBadge")}</span>
                  )}
                  {editedIds.has(sale.id) && <span className="edited-badge inline">{t("editedBadge")}</span>}
                </span>
                <span>{dateToJalaliStr(new Date(sale.created_at))}</span>
                <span>{sale.customer_id ? customerNames[sale.customer_id] ?? "—" : "—"}</span>
                <span>{t(sale.payment_method)}</span>
                <strong>{money(Number(sale.total))}</strong>
                <span className="text-button">{t("viewDetails")} <ChevronLeft size={14} /></span>
              </button>
            ))
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
