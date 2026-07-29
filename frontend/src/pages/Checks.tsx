import { useCallback, useEffect, useState } from "react";
import { ChevronLeft, Search } from "lucide-react";

import { getCheckSummary, getChecks, updateCheckStatus } from "../api";
import { useI18n } from "../i18n";
import type { CheckRead, CheckStatus, CheckSummary } from "../types";
import { isoToJalaliStr } from "../utils/jalali";

type ChecksProps = {
  onViewPurchase: (purchaseId: number) => void;
};

type StatusFilter = "all" | CheckStatus;
type SortOption = "due_asc" | "due_desc" | "amount_desc";

export function Checks({ onViewPurchase }: ChecksProps) {
  const { t, money } = useI18n();
  const [checks, setChecks] = useState<CheckRead[]>([]);
  const [summary, setSummary] = useState<CheckSummary | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("pending");
  const [sort, setSort] = useState<SortOption>("due_asc");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadSummary = useCallback(() => {
    getCheckSummary()
      .then(setSummary)
      .catch(() => setSummary(null));
  }, []);

  useEffect(() => {
    setLoading(true);
    setError("");
    const timeout = window.setTimeout(() => {
      getChecks({ status: statusFilter === "all" ? undefined : statusFilter, sort, search: search || undefined })
        .then(setChecks)
        .catch(() => setError(t("apiError")))
        .finally(() => setLoading(false));
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [statusFilter, sort, search, t]);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  async function handleStatusChange(check: CheckRead, status: CheckStatus) {
    const previous = checks;
    setChecks((current) => current.map((c) => (c.id === check.id ? { ...c, check_status: status } : c)));
    try {
      await updateCheckStatus(check.id, status);
      loadSummary();
    } catch {
      setChecks(previous);
      setError(t("apiError"));
    }
  }

  return (
    <main className="main-content">
      <header className="page-header">
        <div>
          <p className="eyebrow">{t("checks")}</p>
          <h1>{t("checksTitle")}</h1>
          <p>{t("checksSubtitle")}</p>
        </div>
      </header>

      <section className="metric-grid checks-summary-grid">
        <article className="metric-card">
          <p>{t("dueThisWeek")}</p>
          <strong>{summary ? money(Number(summary.due_this_week)) : "—"}</strong>
        </article>
        <article className="metric-card">
          <p>{t("dueThisMonth")}</p>
          <strong>{summary ? money(Number(summary.due_this_month)) : "—"}</strong>
        </article>
      </section>

      {error && <div className="feedback-banner error">{error}</div>}

      <div className="product-filters">
        <label className="search-field">
          <Search size={18} />
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("searchBySupplier")} />
        </label>
        <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}>
          <option value="all">{t("allStatuses")}</option>
          <option value="pending">{t("checkPending")}</option>
          <option value="cleared">{t("checkCleared")}</option>
          <option value="bounced">{t("checkBounced")}</option>
        </select>
        <select value={sort} onChange={(event) => setSort(event.target.value as SortOption)}>
          <option value="due_asc">{t("dueSoonestFirst")}</option>
          <option value="due_desc">{t("dueLatestFirst")}</option>
          <option value="amount_desc">{t("amountHighestFirst")}</option>
        </select>
      </div>

      <div className="panel" style={{ padding: 0, overflow: "hidden" }}>
        <div className="inventory-table">
          <div className="inventory-row inventory-head checks-columns">
            <span>{t("supplier")}</span>
            <span>{t("amount")}</span>
            <span>{t("checkDueDate")}</span>
            <span>{t("checkBankName")}</span>
            <span>{t("checkNumber")}</span>
            <span>{t("invoice")}</span>
            <span>{t("status")}</span>
          </div>

          {loading ? (
            <div className="empty-state compact">{t("loading")}</div>
          ) : checks.length === 0 ? (
            <div className="empty-state compact">{t("noSearchResults")}</div>
          ) : (
            checks.map((check) => (
              <div className="inventory-row checks-columns animated-line" key={check.id}>
                <span>{check.supplier_name ?? "—"}</span>
                <strong>{money(Number(check.amount))}</strong>
                <span>{check.check_due_date ? isoToJalaliStr(check.check_due_date) : "—"}</span>
                <span>{check.check_bank_name ?? "—"}</span>
                <span>{check.check_number ?? "—"}</span>
                <span>
                  {check.purchase_id ? (
                    <button type="button" className="text-button" onClick={() => onViewPurchase(check.purchase_id!)}>
                      {check.purchase_invoice_number ?? "—"} <ChevronLeft size={14} />
                    </button>
                  ) : (
                    "—"
                  )}
                </span>
                <select
                  className={`check-status-select check-status-${check.check_status}`}
                  value={check.check_status}
                  onChange={(event) => handleStatusChange(check, event.target.value as CheckStatus)}
                >
                  <option value="pending">{t("checkPending")}</option>
                  <option value="cleared">{t("checkCleared")}</option>
                  <option value="bounced">{t("checkBounced")}</option>
                </select>
              </div>
            ))
          )}
        </div>
      </div>
    </main>
  );
}
