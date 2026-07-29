import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  CircleDollarSign,
  HandCoins,
  PackageCheck,
  Plus,
  ShoppingCart,
  TriangleAlert,
} from "lucide-react";
import { ProfitChart } from "../components/ProfitChart";

import { getDailySales, getDashboardSummary, getProducts } from "../api";
import { SalesChart } from "../components/SalesChart";
import { SalesComparisonChart, type SalesComparisonPoint } from "../components/SalesComparisonChart";
import { PaymentMethodChart } from "../components/PaymentMethodChart";
import { TopProductsChart } from "../components/TopProductsChart";
import { CheckCalendarWidget } from "../components/CheckCalendarWidget";
import { CheckReminderBanner } from "../components/CheckReminderBanner";
import { CheckTotalsWidget } from "../components/CheckTotalsWidget";
import { DashboardCustomizePanel } from "../components/DashboardCustomizePanel";
import type { Page } from "../components/Sidebar";
import { useI18n } from "../i18n";
import type { DashboardSummary, Product } from "../types";
import { getStockStatus } from "../lib/stockStatus";
import { loadWidgetVisibility, saveWidgetVisibility, type WidgetId } from "../lib/dashboardWidgets";

type DashboardProps = {
  onNavigate: (page: Page) => void;
};

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function shiftedDate(base: Date, days: number): Date {
  const next = new Date(base);
  next.setDate(next.getDate() - days);
  return next;
}

export function Dashboard({ onNavigate }: DashboardProps) {
  const { direction, locale, money, number, t } = useI18n();
  const [products, setProducts] = useState<Product[]>([]);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [comparisonData, setComparisonData] = useState<SalesComparisonPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [visibility, setVisibility] = useState<Record<WidgetId, boolean>>(() => loadWidgetVisibility());
  const Arrow = direction === "rtl" ? ArrowLeft : ArrowRight;

  function toggleWidget(id: WidgetId, visible: boolean) {
    setVisibility((current) => {
      const next = { ...current, [id]: visible };
      saveWidgetVisibility(next);
      return next;
    });
  }

  const needsSummary =
    visibility["kpi-today-sales"] ||
    visibility["kpi-receivables"] ||
    visibility["kpi-active-products"] ||
    visibility["kpi-low-stock"] ||
    visibility["chart-sales-trend"] ||
    visibility["chart-profit-trend"] ||
    visibility["list-top-debtors"] ||
    visibility["list-recent-activity"];
  const needsProducts = visibility["list-low-stock"];
  const needsComparison = visibility["chart-sales-comparison"];

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const [productsData, summaryData] = await Promise.all([
        needsProducts ? getProducts() : Promise.resolve<Product[]>([]),
        needsSummary ? getDashboardSummary() : Promise.resolve<DashboardSummary | null>(null),
      ]);

      setProducts(productsData);
      setSummary(summaryData);
    } catch {
      setError(t("apiError"));
    } finally {
      setLoading(false);
    }
  }, [t, needsProducts, needsSummary]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Sales comparison (current period vs. the equal-length period before it) —
  // fetched independently since it's not part of the bundled summary response.
  useEffect(() => {
    if (!needsComparison) {
      setComparisonData([]);
      return;
    }
    const today = new Date();
    const currentDates = Array.from({ length: 7 }, (_, i) => isoDate(shiftedDate(today, 6 - i)));
    const previousBase = shiftedDate(today, 7);
    const previousDates = Array.from({ length: 7 }, (_, i) => isoDate(shiftedDate(previousBase, 6 - i)));
    const weekdayFormatter = new Intl.DateTimeFormat(locale, {
      weekday: locale.startsWith("fa") ? "narrow" : "short",
    });

    Promise.all([
      getDailySales({ fromDate: currentDates[0], toDate: currentDates[6] }),
      getDailySales({ fromDate: previousDates[0], toDate: previousDates[6] }),
    ])
      .then(([currentRows, previousRows]) => {
        const currentByDate = new Map(currentRows.map((row) => [row.date, Number(row.total_sales)]));
        const previousByDate = new Map(previousRows.map((row) => [row.date, Number(row.total_sales)]));
        setComparisonData(
          currentDates.map((date, i) => ({
            label: weekdayFormatter.format(new Date(date)),
            current: currentByDate.get(date) ?? 0,
            previous: previousByDate.get(previousDates[i]) ?? 0,
          })),
        );
      })
      .catch(() => setComparisonData([]));
  }, [needsComparison, locale]);

  const lowStockProducts = useMemo(
    () =>
      products.filter(
        (product) =>
          Number(product.stock_quantity) <= Number(product.low_stock_threshold),
      ),
    [products],
  );

  const today = new Intl.DateTimeFormat(locale, {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(new Date());

  return (
    <main className="main-content">
      <header className="topbar">
        <div>
          <p className="eyebrow">{today}</p>
          <h1>{t("dashboardTitle")}</h1>
          <p>{t("dashboardSubtitle")}</p>
        </div>

        <div className="topbar-actions dashboard-header-actions">
          <span className="sync-pill">
            {loading || !summary ? t("loading") : `${number(summary.active_products)} ${t("products")}`}
          </span>

          <DashboardCustomizePanel visibility={visibility} onToggle={toggleWidget} />

          <button className="primary-button" onClick={() => onNavigate("sales")}>
            <Plus size={18} />
            {t("sales")}
          </button>
        </div>
      </header>

      {error && <div className="feedback-banner error">{error}</div>}

      <CheckReminderBanner onViewChecks={() => onNavigate("checks")} />

      <section className="metric-grid stagger">
        {visibility["kpi-today-sales"] && (
          <article className="metric-card featured">
            <div className="metric-icon">
              <CircleDollarSign />
            </div>
            <p>{t("todaySales")}</p>
            <strong>{summary ? money(Number(summary.today_sales)) : "—"}</strong>
            <span>
              {summary
                ? `${number(summary.today_transactions)} ${t("transactions")}`
                : t("loading")}
            </span>
          </article>
        )}

        {visibility["kpi-receivables"] && (
          <article className="metric-card">
            <div className="metric-icon">
              <ShoppingCart />
            </div>
            <p>{t("receivables")}</p>
            <strong>{summary ? money(Number(summary.total_receivables)) : "—"}</strong>
            <span>{t("customers")}</span>
          </article>
        )}

        {visibility["kpi-active-products"] && (
          <article className="metric-card">
            <div className="metric-icon">
              <PackageCheck />
            </div>
            <p>{t("activeProducts")}</p>
            <strong>{summary ? number(summary.active_products) : "—"}</strong>
            <span>{t("systemOnline")}</span>
          </article>
        )}

        {visibility["kpi-low-stock"] && (
          <article className="metric-card warning">
            <div className="metric-icon">
              <TriangleAlert />
            </div>
            <p>{t("lowStock")}</p>
            <strong>{summary ? number(summary.low_stock_products) : "—"}</strong>
            <span>{t("requiresAttention")}</span>
          </article>
        )}
      </section>

      {(visibility["chart-sales-trend"] || visibility["chart-profit-trend"] || visibility["list-low-stock"]) && (
        <section className="dashboard-grid">
          {visibility["chart-sales-trend"] && (
            <article className="panel sales-panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">{t("salesTrend")}</p>
                  <h2>{t("thisWeek")}</h2>
                </div>

                <button className="text-button" onClick={() => onNavigate("sales")}>
                  {t("sales")} <Arrow size={16} />
                </button>
              </div>

              <SalesChart summary={summary} />
            </article>
          )}

          {visibility["chart-profit-trend"] && (
            <article className="panel profit-panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">{t("profitTrend")}</p>
                  <h2>{t("profitSubtitle")}</h2>
                </div>
              </div>

              <ProfitChart data={summary?.profit_trend ?? []} />
            </article>
          )}

          {visibility["list-low-stock"] && (
            <article className="panel stock-panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">{t("inventory")}</p>
                  <h2>{t("inventoryAttention")}</h2>
                </div>

                <span className="count-badge">{number(lowStockProducts.length)}</span>
              </div>

              <div className="stock-list">
                {lowStockProducts.slice(0, 5).map((product) => {
                  const stockStatus = getStockStatus(
                    Number(product.stock_quantity),
                    Number(product.low_stock_threshold) || 0,
                  );
                  return (
                    <div className="stock-row" key={product.id}>
                      <span className="product-avatar">{product.name.charAt(0)}</span>
                      <div>
                        <strong>{product.name}</strong>
                        <small>
                          <span className={stockStatus === "ok" ? "stock-value" : `stock-value ${stockStatus}`}>
                            {number(Number(product.stock_quantity))}
                          </span>{" "}
                          {t("available")}
                        </small>
                      </div>
                    </div>
                  );
                })}

                {!loading && lowStockProducts.length === 0 && (
                  <div className="empty-state compact">{t("systemOnline")}</div>
                )}
              </div>

              <button className="full-button" onClick={() => onNavigate("inventory")}>
                {t("inventory")}
              </button>
            </article>
          )}
        </section>
      )}

      {(visibility["chart-sales-comparison"] ||
        visibility["chart-payment-methods"] ||
        visibility["chart-top-products"]) && (
        <section className="dashboard-grid">
          {visibility["chart-sales-comparison"] && (
            <article className="panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">{t("salesTrend")}</p>
                  <h2>{t("salesComparisonTitle")}</h2>
                </div>
              </div>
              <SalesComparisonChart data={comparisonData} />
            </article>
          )}

          {visibility["chart-payment-methods"] && (
            <article className="panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">{t("paymentMethod")}</p>
                  <h2>{t("paymentMethodBreakdownTitle")}</h2>
                </div>
              </div>
              <PaymentMethodChart enabled={visibility["chart-payment-methods"]} />
            </article>
          )}

          {visibility["chart-top-products"] && (
            <article className="panel" style={{ gridColumn: "1 / -1" }}>
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">{t("topSelling")}</p>
                  <h2>{t("topProductsChartTitle")}</h2>
                </div>
              </div>
              <TopProductsChart enabled={visibility["chart-top-products"]} />
            </article>
          )}
        </section>
      )}

      {(visibility["check-calendar"] || visibility["check-totals"]) && (
        <section className="dashboard-grid">
          {visibility["check-calendar"] && (
            <article className="panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">{t("checks")}</p>
                  <h2>{t("checkCalendarTitle")}</h2>
                </div>
                <button className="text-button" onClick={() => onNavigate("checks")}>
                  {t("checks")} <Arrow size={16} />
                </button>
              </div>
              <CheckCalendarWidget onNavigate={onNavigate} />
            </article>
          )}

          {visibility["check-totals"] && (
            <article className="panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">{t("checks")}</p>
                  <h2>{t("checkTotalsWidgetTitle")}</h2>
                </div>
              </div>
              <CheckTotalsWidget />
            </article>
          )}
        </section>
      )}

      {visibility["list-top-debtors"] && summary && summary.top_debtors.length > 0 && (
        <section className="panel debtor-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">{t("receivables")}</p>
              <h2>{t("topDebtors")}</h2>
            </div>

            <span className="count-badge">
              {number(summary.top_debtors.length)}
            </span>
          </div>

          <div className="debtor-list">
            {summary.top_debtors.map((debtor) => (
              <div className="debtor-row" key={debtor.customer_id}>
                <span className="debtor-avatar">{debtor.customer_name.charAt(0)}</span>
                <div>
                  <strong>{debtor.customer_name}</strong>
                  <small>{debtor.phone || "—"}</small>
                </div>
                <strong className="debtor-amount">
                  {money(Number(debtor.balance))}
                </strong>
              </div>
            ))}
          </div>
        </section>
      )}

      {visibility["list-recent-activity"] && summary && summary.recent_customer_activity.length > 0 && (
        <section className="panel activity-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">{t("recentActivity")}</p>
              <h2>{t("latestTransactions")}</h2>
            </div>
          </div>

          <div className="activity-list">
            {summary.recent_customer_activity.slice(0, 6).map((activity, index) => (
              <div className="activity-row" key={`${activity.reference}-${index}`}>
                <span
                  className={`activity-type ${activity.entry_type}`}
                  title={t(activity.entry_type === "sale" ? "sale" : "payment")}
                >
                  {activity.entry_type === "sale" ? <ShoppingCart size={16} /> : <HandCoins size={16} />}
                </span>
                <div>
                  <strong>{activity.customer_name}</strong>
                  <small>{activity.reference}</small>
                </div>
                <span className="activity-amount">
                  {money(Number(activity.amount))}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
