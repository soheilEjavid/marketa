import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ArrowLeft, Award, DollarSign, Gift, Settings2, Sparkles } from "lucide-react";

import {
  adjustLoyaltyPoints,
  getCustomerLedger,
  getErrorMessage,
  getLoyaltyBalance,
  getLoyaltyRewardSuggestions,
  getLoyaltyTransactions,
} from "../api";
import { useI18n } from "../i18n";
import { canAdjustLoyaltyPoints } from "../permissions";
import { getSession } from "../session";
import type { CustomerLedger, LoyaltyBalance, LoyaltyRewardSuggestion, LoyaltyTransaction } from "../types";
import { dateToJalaliStr } from "../utils/jalali";

type CustomerDetailProps = {
  customerId: number;
  customerName: string;
  onBack: () => void;
};

export function CustomerDetail({ customerId, customerName, onBack }: CustomerDetailProps) {
  const { locale, money, number, t } = useI18n();
  const [ledger, setLedger] = useState<CustomerLedger | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [loyalty, setLoyalty] = useState<LoyaltyBalance | null>(null);
  const [loyaltyHistory, setLoyaltyHistory] = useState<LoyaltyTransaction[]>([]);
  const [rewardSuggestions, setRewardSuggestions] = useState<LoyaltyRewardSuggestion[]>([]);
  const [showAllSuggestions, setShowAllSuggestions] = useState(false);
  const [showAdjustForm, setShowAdjustForm] = useState(false);
  const [adjustDelta, setAdjustDelta] = useState("");
  const [adjustReason, setAdjustReason] = useState("");
  const [adjustSubmitting, setAdjustSubmitting] = useState(false);
  const [adjustError, setAdjustError] = useState("");

  const canAdjust = canAdjustLoyaltyPoints(getSession()?.role ?? "");

  const loadLedger = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setLedger(await getCustomerLedger(customerId));
    } catch {
      setError(t("apiError"));
    } finally {
      setLoading(false);
    }
  }, [customerId, t]);

  const loadLoyalty = useCallback(async () => {
    try {
      const [balance, history, suggestions] = await Promise.all([
        getLoyaltyBalance(customerId),
        getLoyaltyTransactions(customerId),
        getLoyaltyRewardSuggestions(customerId),
      ]);
      setLoyalty(balance);
      setLoyaltyHistory(history);
      setRewardSuggestions(suggestions);
    } catch {
      setLoyalty(null);
    }
  }, [customerId]);

  useEffect(() => {
    loadLedger();
    loadLoyalty();
  }, [loadLedger, loadLoyalty]);

  async function handleAdjustSubmit(event: FormEvent) {
    event.preventDefault();
    const delta = Number(adjustDelta);
    if (!delta || !adjustReason.trim()) return;
    setAdjustSubmitting(true);
    setAdjustError("");
    try {
      await adjustLoyaltyPoints(customerId, delta, adjustReason.trim());
      setAdjustDelta("");
      setAdjustReason("");
      setShowAdjustForm(false);
      await loadLoyalty();
    } catch (err) {
      setAdjustError(getErrorMessage(err, t));
    } finally {
      setAdjustSubmitting(false);
    }
  }

  const transactionTypeLabel: Record<string, string> = {
    earn: t("pointsEarn"),
    redeem: t("pointsRedeem"),
    expire: t("pointsExpire"),
    adjust: t("pointsAdjust"),
  };

  return (
    <main className="main-content">
      <header className="page-header">
        <div>
          <p className="eyebrow">{t("customers")}</p>
          <h1>{customerName}</h1>
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
            <article className="metric-card">
              <div className="metric-icon"><Gift /></div>
              <p>{t("loyaltyPoints")}</p>
              <strong>{loyalty ? number(loyalty.points_balance) : "—"}</strong>
              {loyalty && loyalty.points_balance > 0 && (
                <small className="muted-text">{money(Number(loyalty.points_value_toman))}</small>
              )}
              {loyalty && (
                <span className={`status-pill ${loyalty.is_member ? "active" : ""}`}>
                  {t(loyalty.is_member ? "loyaltyMember" : "loyaltyNotYetMember")}
                </span>
              )}
              {loyalty && (
                <span className={`tier-badge tier-${loyalty.tier}`}>
                  <Award size={13} /> {t(`tier_${loyalty.tier}`)}
                </span>
              )}
            </article>
            {canAdjust && (
              <article className="metric-card metric-card-centered">
                <div className="metric-icon"><Settings2 /></div>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => setShowAdjustForm((current) => !current)}
                >
                  {t("adjustPoints")}
                </button>
              </article>
            )}
          </section>

          {showAdjustForm && canAdjust && (
            <section className="panel" style={{ marginBottom: 16 }}>
              <form className="form-grid" onSubmit={handleAdjustSubmit}>
                {adjustError && <div className="feedback-banner error full-span">{adjustError}</div>}
                <label className="field">
                  <span>{t("adjustPointsDelta")}</span>
                  <input
                    type="number"
                    value={adjustDelta}
                    onChange={(event) => setAdjustDelta(event.target.value)}
                    placeholder="+10 / -10"
                    required
                  />
                </label>
                <label className="field">
                  <span>{t("adjustPointsReason")}</span>
                  <input
                    type="text"
                    value={adjustReason}
                    onChange={(event) => setAdjustReason(event.target.value)}
                    placeholder={t("adjustPointsReasonPlaceholder")}
                    minLength={3}
                    required
                  />
                </label>
                <div className="form-actions full-span">
                  <button className="primary-button" type="submit" disabled={adjustSubmitting}>
                    {adjustSubmitting ? t("loading") : t("applyAdjustment")}
                  </button>
                </div>
              </form>
            </section>
          )}

          {rewardSuggestions.length > 0 && (
            <section className="panel" style={{ marginBottom: 16 }}>
              <div className="panel-heading">
                <h2>
                  <Sparkles size={16} style={{ verticalAlign: "middle", marginInlineEnd: 6 }} />
                  {t("rewardSuggestions")}
                </h2>
                <span className="subtle-chip">{t("rewardSuggestionsSubtitle")}</span>
              </div>
              <div className="report-table">
                <div className="report-table-row report-cols-4 report-head">
                  <span className="report-header-cell">{t("productName")}</span>
                  <span className="report-header-cell">{t("salePrice")}</span>
                  <span className="report-header-cell">{t("pointsRequired")}</span>
                  <span className="report-header-cell">{t("rewardReason")}</span>
                </div>
                {(showAllSuggestions ? rewardSuggestions : rewardSuggestions.slice(0, 6)).map((row) => (
                  <div className="report-table-row report-cols-4 animated-line" key={row.product_id}>
                    <strong>{row.product_name}</strong>
                    <span>{money(Number(row.sale_price))}</span>
                    <span className={row.affordable ? "quantity-positive" : "muted-text"}>
                      {number(row.points_required)}
                    </span>
                    <span className="subtle-chip">
                      {row.reason === "near_expiry" ? t("rewardReasonNearExpiry") : t("rewardReasonDeadStock")}
                    </span>
                  </div>
                ))}
              </div>
              {rewardSuggestions.length > 6 && (
                <button
                  type="button"
                  className="text-button"
                  style={{ marginTop: 10 }}
                  onClick={() => setShowAllSuggestions((current) => !current)}
                >
                  {showAllSuggestions
                    ? t("showFewer")
                    : t("showAllCount").replace("{count}", String(rewardSuggestions.length))}
                </button>
              )}
            </section>
          )}

          {loyaltyHistory.length > 0 && (
            <section className="panel" style={{ marginBottom: 16 }}>
              <div className="panel-heading">
                <h2>{t("pointsHistory")}</h2>
              </div>
              <div className="report-table">
                <div className="report-table-row report-cols-4 report-head">
                  <span className="report-header-cell">{t("date")}</span>
                  <span className="report-header-cell">{t("type")}</span>
                  <span className="report-header-cell">{t("loyaltyPoints")}</span>
                  <span className="report-header-cell">{t("adjustPointsReason")}</span>
                </div>
                {loyaltyHistory.map((entry) => (
                  <div className="report-table-row report-cols-4 animated-line" key={entry.id}>
                    <span className="report-date-cell">{dateToJalaliStr(new Date(entry.created_at))}</span>
                    <span>{transactionTypeLabel[entry.transaction_type] ?? entry.transaction_type}</span>
                    <strong className={entry.points >= 0 ? "quantity-positive" : "quantity-negative"}>
                      {entry.points >= 0 ? "+" : ""}
                      {number(entry.points)}
                    </strong>
                    <span className="muted-text">{entry.reason ?? "—"}</span>
                  </div>
                ))}
              </div>
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
                  {t(entry.entry_type === "sale" ? "sale" : entry.entry_type === "payment" ? "payment" : "purchase")}
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
