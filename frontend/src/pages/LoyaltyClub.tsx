import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  Award,
  Cake,
  CalendarDays,
  Clock,
  DollarSign,
  Gift,
  Package,
  Search,
  Sparkles,
  TrendingDown,
  UsersRound,
} from "lucide-react";

import {
  getChurnRiskCustomers,
  getCustomerTiers,
  getErrorMessage,
  getLoyaltyLiability,
  getLoyaltySettings,
  getRewardCatalog,
  getUpcomingBirthdays,
  issueChurnRecoveryCoupons,
  updateLoyaltySettings,
} from "../api";
import { useI18n } from "../i18n";
import { canAdjustLoyaltyPoints } from "../permissions";
import { getSession } from "../session";
import type {
  BirthdayCustomerRow,
  ChurnRiskCustomerRow,
  CustomerTierRow,
  LoyaltyLiabilityRow,
  LoyaltyRewardCatalogRow,
} from "../types";
import { isoToJalaliStr, timestampToJalaliStr } from "../utils/jalali";

function reportBadgeClass(value: number): string {
  if (value > 0) return "metric-badge metric-badge-success";
  if (value < 0) return "metric-badge metric-badge-danger";
  return "metric-badge metric-badge-neutral";
}

export function LoyaltyClub() {
  const { money, number, t } = useI18n();
  const canManageLoyaltySettings = canAdjustLoyaltyPoints(getSession()?.role ?? "");

  const renderMoney = useMemo(
    () => (value: number | string | null | undefined) => money(Number(value ?? 0)),
    [money],
  );

  const [loyaltyLiabilityRows, setLoyaltyLiabilityRows] = useState<LoyaltyLiabilityRow[]>([]);
  const [birthdayRows, setBirthdayRows] = useState<BirthdayCustomerRow[]>([]);
  const [churnRiskRows, setChurnRiskRows] = useState<ChurnRiskCustomerRow[]>([]);
  const [tierRows, setTierRows] = useState<CustomerTierRow[]>([]);
  const [showAllTiers, setShowAllTiers] = useState(false);
  const [loyaltyLoading, setLoyaltyLoading] = useState(true);

  const [minInvoiceTotalInput, setMinInvoiceTotalInput] = useState("");
  const [minInvoiceProfitInput, setMinInvoiceProfitInput] = useState("");
  const [tierSilverInput, setTierSilverInput] = useState("");
  const [tierGoldInput, setTierGoldInput] = useState("");
  const [tierWindowDaysInput, setTierWindowDaysInput] = useState("");
  const [tierSilverBonusInput, setTierSilverBonusInput] = useState("");
  const [tierGoldBonusInput, setTierGoldBonusInput] = useState("");
  const [churnCouponPointsInput, setChurnCouponPointsInput] = useState("");
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [settingsMessage, setSettingsMessage] = useState("");
  const [settingsError, setSettingsError] = useState("");

  const [issuingCoupons, setIssuingCoupons] = useState(false);
  const [couponMessage, setCouponMessage] = useState("");

  const [catalogRows, setCatalogRows] = useState<LoyaltyRewardCatalogRow[]>([]);
  const [catalogSearch, setCatalogSearch] = useState("");
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [showAllCatalog, setShowAllCatalog] = useState(false);

  const loadLoyalty = useCallback(async () => {
    setLoyaltyLoading(true);
    try {
      const [liability, birthdays, churnRisk, settings, tiers] = await Promise.all([
        getLoyaltyLiability(),
        getUpcomingBirthdays(),
        getChurnRiskCustomers(),
        getLoyaltySettings(),
        getCustomerTiers(),
      ]);
      setLoyaltyLiabilityRows(liability);
      setBirthdayRows(birthdays);
      setChurnRiskRows(churnRisk);
      setMinInvoiceTotalInput(settings.min_invoice_total_for_membership ?? "");
      setMinInvoiceProfitInput(settings.min_invoice_profit_for_membership ?? "");
      setTierSilverInput(settings.tier_silver_min_spend ?? "");
      setTierGoldInput(settings.tier_gold_min_spend ?? "");
      setTierWindowDaysInput(settings.tier_window_days?.toString() ?? "");
      setTierSilverBonusInput(settings.tier_silver_earn_bonus ?? "");
      setTierGoldBonusInput(settings.tier_gold_earn_bonus ?? "");
      setChurnCouponPointsInput(settings.churn_recovery_coupon_points?.toString() ?? "");
      setTierRows(tiers);
    } catch {
      setLoyaltyLiabilityRows([]);
      setBirthdayRows([]);
      setChurnRiskRows([]);
      setTierRows([]);
    } finally {
      setLoyaltyLoading(false);
    }
  }, []);

  useEffect(() => {
    loadLoyalty();
  }, [loadLoyalty]);

  async function handleSaveLoyaltySettings(event: FormEvent) {
    event.preventDefault();
    setSettingsSaving(true);
    setSettingsError("");
    setSettingsMessage("");
    try {
      const updated = await updateLoyaltySettings({
        min_invoice_total_for_membership: minInvoiceTotalInput.trim() || null,
        min_invoice_profit_for_membership: minInvoiceProfitInput.trim() || null,
        tier_silver_min_spend: tierSilverInput.trim() || null,
        tier_gold_min_spend: tierGoldInput.trim() || null,
        tier_window_days: tierWindowDaysInput.trim() ? Number(tierWindowDaysInput) : null,
        tier_silver_earn_bonus: tierSilverBonusInput.trim() || null,
        tier_gold_earn_bonus: tierGoldBonusInput.trim() || null,
        churn_recovery_coupon_points: churnCouponPointsInput.trim() ? Number(churnCouponPointsInput) : null,
      });
      setMinInvoiceTotalInput(updated.min_invoice_total_for_membership ?? "");
      setMinInvoiceProfitInput(updated.min_invoice_profit_for_membership ?? "");
      setTierSilverInput(updated.tier_silver_min_spend ?? "");
      setTierGoldInput(updated.tier_gold_min_spend ?? "");
      setTierWindowDaysInput(updated.tier_window_days?.toString() ?? "");
      setTierSilverBonusInput(updated.tier_silver_earn_bonus ?? "");
      setTierGoldBonusInput(updated.tier_gold_earn_bonus ?? "");
      setChurnCouponPointsInput(updated.churn_recovery_coupon_points?.toString() ?? "");
      setSettingsMessage(t("loyaltySettingsSaved"));
      await loadLoyalty();
    } catch (err) {
      setSettingsError(getErrorMessage(err, t));
    } finally {
      setSettingsSaving(false);
    }
  }

  async function handleIssueChurnCoupons() {
    setIssuingCoupons(true);
    setCouponMessage("");
    try {
      const issued = await issueChurnRecoveryCoupons();
      setCouponMessage(
        issued.length > 0
          ? t("churnCouponsIssuedCount").replace("{count}", String(issued.length))
          : t("churnCouponsNoneIssued"),
      );
      await loadLoyalty();
    } catch (err) {
      setCouponMessage(getErrorMessage(err, t));
    } finally {
      setIssuingCoupons(false);
    }
  }

  const loadCatalog = useCallback(async (search: string) => {
    setCatalogLoading(true);
    try {
      setCatalogRows(await getRewardCatalog(search));
    } catch {
      setCatalogRows([]);
    } finally {
      setCatalogLoading(false);
    }
  }, []);

  useEffect(() => {
    const timeout = window.setTimeout(() => loadCatalog(catalogSearch), 250);
    return () => window.clearTimeout(timeout);
  }, [loadCatalog, catalogSearch]);

  return (
    <main className="main-content">
      <header className="page-header">
        <div>
          <p className="eyebrow">{t("customers")}</p>
          <h1>{t("loyaltyProgram")}</h1>
          <p>{t("loyaltyClubSubtitle")}</p>
        </div>
      </header>

      {canManageLoyaltySettings && (
        <section className="panel" style={{ marginBottom: 16 }}>
          <div className="panel-heading">
            <h2>{t("loyaltySettingsTitle")}</h2>
            <span className="subtle-chip">{t("loyaltySettingsSubtitle")}</span>
          </div>
          <form className="form-grid" onSubmit={handleSaveLoyaltySettings}>
            {settingsError && <div className="feedback-banner error full-span">{settingsError}</div>}
            {settingsMessage && <div className="feedback-banner success full-span">{settingsMessage}</div>}
            <label className="field">
              <span>{t("minInvoiceTotalForMembership")} ({t("optional")})</span>
              <input
                type="number"
                min="0"
                value={minInvoiceTotalInput}
                onChange={(event) => setMinInvoiceTotalInput(event.target.value)}
                placeholder={t("loyaltySettingsDisabledPlaceholder")}
              />
            </label>
            <label className="field">
              <span>{t("minInvoiceProfitForMembership")} ({t("optional")})</span>
              <input
                type="number"
                min="0"
                value={minInvoiceProfitInput}
                onChange={(event) => setMinInvoiceProfitInput(event.target.value)}
                placeholder={t("loyaltySettingsDisabledPlaceholder")}
              />
            </label>
            <label className="field">
              <span>{t("tierSilverMinSpend")} ({t("optional")})</span>
              <input
                type="number"
                min="0"
                value={tierSilverInput}
                onChange={(event) => setTierSilverInput(event.target.value)}
                placeholder={t("loyaltySettingsDisabledPlaceholder")}
              />
            </label>
            <label className="field">
              <span>{t("tierGoldMinSpend")} ({t("optional")})</span>
              <input
                type="number"
                min="0"
                value={tierGoldInput}
                onChange={(event) => setTierGoldInput(event.target.value)}
                placeholder={t("loyaltySettingsDisabledPlaceholder")}
              />
            </label>
            <label className="field">
              <span>{t("tierWindowDays")} ({t("optional")})</span>
              <input
                type="number"
                min="1"
                value={tierWindowDaysInput}
                onChange={(event) => setTierWindowDaysInput(event.target.value)}
                placeholder={t("tierWindowDaysPlaceholder")}
              />
            </label>
            <label className="field">
              <span>{t("tierSilverEarnBonus")} ({t("optional")})</span>
              <input
                type="number"
                min="0"
                step="0.1"
                value={tierSilverBonusInput}
                onChange={(event) => setTierSilverBonusInput(event.target.value)}
                placeholder={t("tierEarnBonusPlaceholder")}
              />
            </label>
            <label className="field">
              <span>{t("tierGoldEarnBonus")} ({t("optional")})</span>
              <input
                type="number"
                min="0"
                step="0.1"
                value={tierGoldBonusInput}
                onChange={(event) => setTierGoldBonusInput(event.target.value)}
                placeholder={t("tierEarnBonusPlaceholder")}
              />
            </label>
            <label className="field">
              <span>{t("churnRecoveryCouponPoints")} ({t("optional")})</span>
              <input
                type="number"
                min="0"
                value={churnCouponPointsInput}
                onChange={(event) => setChurnCouponPointsInput(event.target.value)}
                placeholder={t("loyaltySettingsDisabledPlaceholder")}
              />
            </label>
            <div className="form-actions full-span">
              <button className="primary-button" type="submit" disabled={settingsSaving}>
                {settingsSaving ? t("loading") : t("save")}
              </button>
            </div>
          </form>
        </section>
      )}

      <section className="panel report-table-wrap">
        <div className="panel-heading">
          <div>
            <h2>{t("loyaltyLiability")}</h2>
            <span className="subtle-chip" style={{ marginTop: 6, display: "inline-block" }}>
              {t("loyaltyLiabilitySubtitle")}
            </span>
          </div>
        </div>
        <div className="report-table">
          <div className="report-table-row report-cols-3 report-head">
            <span className="report-header-cell">
              <UsersRound size={14} strokeWidth={1.8} />
              {t("fullName")}
            </span>
            <span className="report-header-cell">
              <Gift size={14} strokeWidth={1.8} />
              {t("loyaltyPoints")}
            </span>
            <span className="report-header-cell">
              <DollarSign size={14} strokeWidth={1.8} />
              {t("pointsValue")}
            </span>
          </div>
          {loyaltyLoading ? (
            <div className="empty-state compact">{t("loading")}</div>
          ) : loyaltyLiabilityRows.length > 0 ? (
            loyaltyLiabilityRows.map((row) => (
              <div className="report-table-row report-cols-3 animated-line" key={row.customer_id}>
                <strong>{row.customer_name}</strong>
                <span className="muted-text">{number(row.points_balance)}</span>
                <strong className="metric-badge metric-badge-danger">
                  {renderMoney(Number(row.points_value_toman))}
                </strong>
              </div>
            ))
          ) : (
            <div className="empty-state compact">{t("noLoyaltyLiability")}</div>
          )}
        </div>
      </section>

      {tierRows.length > 0 && (
        <section className="panel report-table-wrap" style={{ marginTop: 16 }}>
          <div className="panel-heading">
            <h2>
              <Award size={16} style={{ verticalAlign: "middle", marginInlineEnd: 6 }} />
              {t("customerTiers")}
            </h2>
            <span className="subtle-chip">{t("customerTiersSubtitle")}</span>
          </div>
          <div className="report-table">
            <div className="report-table-row report-cols-3 report-head">
              <span className="report-header-cell">
                <UsersRound size={14} strokeWidth={1.8} />
                {t("fullName")}
              </span>
              <span className="report-header-cell">
                <DollarSign size={14} strokeWidth={1.8} />
                {t("lifetimeSpend")}
              </span>
              <span className="report-header-cell">
                <Award size={14} strokeWidth={1.8} />
                {t("tier")}
              </span>
            </div>
            {(showAllTiers ? tierRows : tierRows.slice(0, 8)).map((row) => (
              <div className="report-table-row report-cols-3 animated-line" key={row.customer_id}>
                <strong>{row.customer_name}</strong>
                <span className="muted-text">{renderMoney(Number(row.lifetime_spend))}</span>
                <span className={`tier-badge tier-${row.tier}`}>{t(`tier_${row.tier}`)}</span>
              </div>
            ))}
          </div>
          {tierRows.length > 8 && (
            <button
              type="button"
              className="text-button"
              style={{ marginTop: 10 }}
              onClick={() => setShowAllTiers((current) => !current)}
            >
              {showAllTiers ? t("showFewer") : t("showAllCount").replace("{count}", String(tierRows.length))}
            </button>
          )}
        </section>
      )}

      <section className="panel report-table-wrap" style={{ marginTop: 16 }}>
        <div className="panel-heading">
          <h2>{t("upcomingBirthdays")}</h2>
          <span className="subtle-chip">{t("upcomingBirthdaysSubtitle")}</span>
        </div>
        <div className="report-table">
          <div className="report-table-row report-cols-3 report-head">
            <span className="report-header-cell">
              <UsersRound size={14} strokeWidth={1.8} />
              {t("fullName")}
            </span>
            <span className="report-header-cell">
              <Cake size={14} strokeWidth={1.8} />
              {t("birthDate")}
            </span>
            <span className="report-header-cell">
              <Clock size={14} strokeWidth={1.8} />
              {t("daysUntilBirthday")}
            </span>
          </div>
          {loyaltyLoading ? (
            <div className="empty-state compact">{t("loading")}</div>
          ) : birthdayRows.length > 0 ? (
            birthdayRows.map((row) => (
              <div className="report-table-row report-cols-3 animated-line" key={row.customer_id}>
                <strong>{row.customer_name}</strong>
                <span className="report-date-cell">{isoToJalaliStr(row.birth_date)}</span>
                <span className={reportBadgeClass(row.days_until_birthday === 0 ? 1 : -1)}>
                  {number(row.days_until_birthday)}
                </span>
              </div>
            ))
          ) : (
            <div className="empty-state compact">{t("noUpcomingBirthdays")}</div>
          )}
        </div>
      </section>

      <section className="panel report-table-wrap" style={{ marginTop: 16 }}>
        <div className="panel-heading">
          <div>
            <h2>{t("churnRisk")}</h2>
            <span className="subtle-chip">{t("churnRiskSubtitle")}</span>
          </div>
          {canManageLoyaltySettings && churnRiskRows.length > 0 && (
            <button
              type="button"
              className="secondary-button"
              disabled={issuingCoupons}
              onClick={handleIssueChurnCoupons}
            >
              <Sparkles size={16} /> {issuingCoupons ? t("loading") : t("issueChurnCoupons")}
            </button>
          )}
        </div>
        {couponMessage && <div className="feedback-banner success" style={{ marginBottom: 12 }}>{couponMessage}</div>}
        <div className="report-table">
          <div className="report-table-row report-cols-4 report-head">
            <span className="report-header-cell">
              <UsersRound size={14} strokeWidth={1.8} />
              {t("fullName")}
            </span>
            <span className="report-header-cell">
              <TrendingDown size={14} strokeWidth={1.8} />
              {t("recentPurchaseCount")}
            </span>
            <span className="report-header-cell">
              <CalendarDays size={14} strokeWidth={1.8} />
              {t("lastPurchase")}
            </span>
            <span className="report-header-cell">
              <Clock size={14} strokeWidth={1.8} />
              {t("daysSinceLastPurchase")}
            </span>
          </div>
          {loyaltyLoading ? (
            <div className="empty-state compact">{t("loading")}</div>
          ) : churnRiskRows.length > 0 ? (
            churnRiskRows.map((row) => (
              <div className="report-table-row report-cols-4 animated-line" key={row.customer_id}>
                <strong>{row.customer_name}</strong>
                <span className="muted-text">{number(row.purchase_count_recent)}</span>
                <span className="report-date-cell">{timestampToJalaliStr(row.last_purchase_at)}</span>
                <strong className="metric-badge metric-badge-danger">
                  {number(row.days_since_last_purchase)}
                </strong>
              </div>
            ))
          ) : (
            <div className="empty-state compact">{t("noChurnRiskCustomers")}</div>
          )}
        </div>
      </section>

      <section className="panel report-table-wrap" style={{ marginTop: 16 }}>
        <div className="panel-heading">
          <div>
            <h2>{t("rewardCatalog")}</h2>
            <span className="subtle-chip">{t("rewardCatalogSubtitle")}</span>
          </div>
          <label className="search-field" style={{ maxWidth: 240 }}>
            <Search size={16} />
            <input
              value={catalogSearch}
              onChange={(event) => setCatalogSearch(event.target.value)}
              placeholder={t("searchProductsCatalog")}
            />
          </label>
        </div>
        <div className="report-table">
          <div className="report-table-row report-cols-3 report-head">
            <span className="report-header-cell">
              <Package size={14} strokeWidth={1.8} />
              {t("productName")}
            </span>
            <span className="report-header-cell">
              <Gift size={14} strokeWidth={1.8} />
              {t("pointsRequired")}
            </span>
            <span className="report-header-cell">
              <Sparkles size={14} strokeWidth={1.8} />
              {t("rewardReason")}
            </span>
          </div>
          {catalogLoading ? (
            <div className="empty-state compact">{t("loading")}</div>
          ) : catalogRows.length > 0 ? (
            (showAllCatalog ? catalogRows : catalogRows.slice(0, 15)).map((row) => (
              <div className="report-table-row report-cols-3 animated-line" key={row.product_id}>
                <strong>{row.product_name}</strong>
                <span className="muted-text">{number(row.points_required)}</span>
                {row.is_suggested ? (
                  <span className="subtle-chip">
                    {row.reason === "near_expiry" ? t("rewardReasonNearExpiry") : t("rewardReasonDeadStock")}
                  </span>
                ) : (
                  <span className="muted-text">—</span>
                )}
              </div>
            ))
          ) : (
            <div className="empty-state compact">{t("noRewardCatalogItems")}</div>
          )}
        </div>
        {catalogRows.length > 15 && (
          <button
            type="button"
            className="text-button"
            style={{ marginTop: 10 }}
            onClick={() => setShowAllCatalog((current) => !current)}
          >
            {showAllCatalog ? t("showFewer") : t("showAllCount").replace("{count}", String(catalogRows.length))}
          </button>
        )}
      </section>
    </main>
  );
}
