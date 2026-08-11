import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  Boxes,
  CalendarClock,
  CalendarDays,
  ChevronLeft,
  CircleDollarSign,
  Clock,
  DollarSign,
  Gift,
  Info,
  Moon,
  Package,
  Percent,
  ReceiptText,
  TrendingUp,
  UserRound,
  Wallet,
  UsersRound,
} from "lucide-react";

import {
  getCashierPerformance,
  getInflationRate,
  getLoyaltyRedemptions,
  getNearExpiryProducts,
  getNetProfit,
  getSalesPage,
  getShifts,
  request,
} from "../api";
import { JalaliDatePicker } from "../components/JalaliDatePicker";
import { PeriodLabel, PeriodSelector, defaultPeriod, type Period } from "../components/PeriodSelector";
import { SaleDetailView } from "../components/SaleDetailView";
import type { Page } from "../components/Sidebar";
import { useI18n } from "../i18n";
import { calculateInvoiceMargin, calculateMarginPct, formatMarginPct, getMarginStatus } from "../lib/margin";
import { canManageExpenses } from "../permissions";
import { getSession } from "../session";
import { getJalaliMonthDays, isoToJalaliStr, localIsoDate, parseJalaliDateString, timestampToJalaliStr, timestampToLocalTime, toGregorian, todayJalali } from "../utils/jalali";
import type {
  CashierPerformanceRow,
  CashierShift,
  DeadStockRow,
  InflationRateReport,
  LoyaltyRedemptionRow,
  NearExpiryRow,
  NetProfitReport,
  Sale,
} from "../types";

type ReportTab =
  | "sales"
  | "products"
  | "stock"
  | "dead-stock"
  | "near-expiry"
  | "inflation-rate"
  | "cashiers"
  | "balances"
  | "loyalty";

type DailySalesRow = {
  date: string;
  total_sales: string;
  transaction_count: number;
  average_ticket: string;
  profit: string;
};

type TopProduct = {
  product_id: number;
  product_name: string;
  total_quantity: string;
  total_revenue: string;
  total_profit: string;
};

type LowStockItem = {
  product_id: number;
  product_name: string;
  stock_quantity: string;
  low_stock_threshold: string;
};

type InvItem = {
  product_id: number;
  product_name: string;
  stock_quantity: string;
  purchase_price: string;
  sale_price: string;
  total_stock_value: string;
  potential_profit: string | null;
};

type BalItem = {
  customer_id?: number;
  customer_name?: string;
  supplier_id?: number;
  supplier_name?: string;
  balance: string;
  credit_limit: string;
};

type ReportTabDefinition = {
  key: ReportTab;
  label: string;
  Icon: typeof BarChart3;
};

const API_BASE = import.meta.env.VITE_API_URL ?? "/api/v1";

function formatMoney(value: number, money: (value: number) => string): string {
  return money(Number.isFinite(value) ? value : 0);
}

function reportBadgeClass(value: number): string {
  if (value > 0) {
    return "metric-badge metric-badge-success";
  }
  if (value < 0) {
    return "metric-badge metric-badge-danger";
  }
  return "metric-badge metric-badge-neutral";
}

/** Same rounding convention as formatMarginPct (lib/margin.ts) — always
 * shows an explicit +/- sign so a decline never reads as a bare, confusing
 * negative number (see docs/inflation-rate-report.md). */
function formatSignedPct(value: number, numberFn: (value: number) => string): string {
  const rounded = Math.round(value * 10) / 10;
  const safeRounded = Object.is(rounded, -0) ? 0 : rounded;
  const sign = safeRounded > 0 ? "+" : safeRounded < 0 ? "−" : "";
  return `${sign}${numberFn(Math.abs(safeRounded))}٪`;
}

const tabs: ReportTabDefinition[] = [
  { key: "sales", label: "sales", Icon: BarChart3 },
  { key: "products", label: "products", Icon: TrendingUp },
  { key: "stock", label: "inventory", Icon: ReceiptText },
  { key: "dead-stock", label: "deadStockTitle", Icon: Moon },
  { key: "near-expiry", label: "nearExpiryTitle", Icon: CalendarClock },
  { key: "inflation-rate", label: "inflationRateTitle", Icon: Percent },
  { key: "cashiers", label: "cashierPerformance", Icon: UserRound },
  { key: "balances", label: "balances", Icon: UsersRound },
  { key: "loyalty", label: "loyaltyRedemptions", Icon: Gift },
];

function toIsoDate(gy: number, gm: number, gd: number): string {
  return `${gy}-${String(gm).padStart(2, "0")}-${String(gd).padStart(2, "0")}`;
}

/** "این ماه در مقابل ماه قبل" / "امسال در مقابل پارسال" period presets,
 * computed on the Jalali calendar (this app's primary calendar) then
 * converted to the ISO dates the API expects. */
function jalaliPresetRange(preset: "this-month-vs-last" | "this-year-vs-last"): {
  period1Start: string;
  period1End: string;
  period2Start: string;
  period2End: string;
} {
  const todayParsed = parseJalaliDateString(todayJalali())!;
  const { year: ty, month: tm, day: td } = todayParsed;

  if (preset === "this-month-vs-last") {
    let lastMonthYear = ty;
    let lastMonth = tm - 1;
    if (lastMonth === 0) {
      lastMonth = 12;
      lastMonthYear -= 1;
    }
    const lastMonthDays = getJalaliMonthDays(lastMonthYear, lastMonth);
    // Cap period 1 at the SAME day-count as period 2 (which always stops at
    // today, since the current month isn't over yet). Comparing a full
    // 31-day month against an in-progress ~13-day month would always show
    // a large apparent revenue "decline" in period 2 — not because of any
    // real business change, just because fewer days have elapsed. A fair
    // like-for-like comparison needs equal day counts on both sides.
    const period1Day = Math.min(td, lastMonthDays);
    return {
      period1Start: toIsoDate(...toGregorian(lastMonthYear, lastMonth, 1)),
      period1End: toIsoDate(...toGregorian(lastMonthYear, lastMonth, period1Day)),
      period2Start: toIsoDate(...toGregorian(ty, tm, 1)),
      period2End: toIsoDate(...toGregorian(ty, tm, td)),
    };
  }

  return {
    period1Start: toIsoDate(...toGregorian(ty - 1, 1, 1)),
    period1End: toIsoDate(...toGregorian(ty - 1, tm, td)),
    period2Start: toIsoDate(...toGregorian(ty, 1, 1)),
    period2End: toIsoDate(...toGregorian(ty, tm, td)),
  };
}

type ReportsProps = {
  onNavigate?: (page: Page) => void;
};

export function Reports({ onNavigate }: ReportsProps = {}) {
  const { money, number, t, language } = useI18n();

  const [tab, setTab] = useState<ReportTab>("sales");
  const [salesPeriod, setSalesPeriod] = useState<Period>(() => defaultPeriod());
  const [dailySales, setDailySales] = useState<DailySalesRow[]>([]);
  const [topProducts, setTopProducts] = useState<TopProduct[]>([]);
  const [lowStock, setLowStock] = useState<LowStockItem[]>([]);
  const [inventory, setInventory] = useState<InvItem[]>([]);
  const [customerBals, setCustomerBals] = useState<BalItem[]>([]);
  const [supplierBals, setSupplierBals] = useState<BalItem[]>([]);
  const [deadStock, setDeadStock] = useState<DeadStockRow[]>([]);
  const [deadStockLookback, setDeadStockLookback] = useState<30 | 60 | 90>(30);
  const [deadStockLoading, setDeadStockLoading] = useState(true);
  const [nearExpiry, setNearExpiry] = useState<NearExpiryRow[]>([]);
  const [nearExpiryLoading, setNearExpiryLoading] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [invoiceList, setInvoiceList] = useState<Sale[]>([]);
  const [invoiceListLoading, setInvoiceListLoading] = useState(true);
  const [viewingSaleId, setViewingSaleId] = useState<number | null>(null);
  const [redemptionRows, setRedemptionRows] = useState<LoyaltyRedemptionRow[]>([]);
  const [redemptionLoading, setRedemptionLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const base = `${API_BASE}/reports`;
      const [
        sales,
        products,
        stockItems,
        inv,
        customerBalances,
        supplierBalances,
      ] = await Promise.all([
        request<DailySalesRow[]>(
          `${base}/daily-sales?from_date=${salesPeriod.start}&to_date=${salesPeriod.end}`,
        ),
        request<TopProduct[]>(`${base}/top-products`),
        request<LowStockItem[]>(`${base}/low-stock`),
        request<InvItem[]>(`${base}/inventory`),
        request<BalItem[]>(`${base}/customer-balances`),
        request<BalItem[]>(`${base}/supplier-balances`),
      ]);

      setDailySales(sales);
      setTopProducts(products);
      setLowStock(stockItems);
      setInventory(inv);
      setCustomerBals(customerBalances);
      setSupplierBals(supplierBalances);
    } catch {
      setError(t("apiError"));
    } finally {
      setLoading(false);
    }
  }, [t, salesPeriod.start, salesPeriod.end]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Gross profit, operating expenses and net profit must always describe the
  // SAME days as the daily-sales table under them, or the net figure is
  // arithmetic nonsense. One piece of state drives all four, so they cannot
  // drift apart.
  const canSeeNetProfit = canManageExpenses(getSession()?.role ?? "");
  const [netProfitReport, setNetProfitReport] = useState<NetProfitReport | null>(null);

  useEffect(() => {
    if (!canSeeNetProfit) return;
    getNetProfit({ periodStart: salesPeriod.start, periodEnd: salesPeriod.end })
      .then(setNetProfitReport)
      .catch(() => setNetProfitReport(null));
  }, [canSeeNetProfit, salesPeriod.start, salesPeriod.end]);

  const loadInvoiceList = useCallback(async () => {
    setInvoiceListLoading(true);
    try {
      const result = await getSalesPage({ sort: "date_desc", limit: 20 });
      setInvoiceList(result.items);
    } catch {
      setInvoiceList([]);
    } finally {
      setInvoiceListLoading(false);
    }
  }, []);

  useEffect(() => {
    loadInvoiceList();
  }, [loadInvoiceList]);

  const loadRedemptions = useCallback(async () => {
    setRedemptionLoading(true);
    try {
      setRedemptionRows(await getLoyaltyRedemptions());
    } catch {
      setRedemptionRows([]);
    } finally {
      setRedemptionLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRedemptions();
  }, [loadRedemptions]);

  const loadDeadStock = useCallback(async (days: number) => {
    setDeadStockLoading(true);
    try {
      const rows = await request<DeadStockRow[]>(`${API_BASE}/reports/dead-stock?lookback_days=${days}`);
      setDeadStock(rows);
    } catch {
      setDeadStock([]);
    } finally {
      setDeadStockLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDeadStock(deadStockLookback);
  }, [loadDeadStock, deadStockLookback]);

  const totalValueTiedUp = useMemo(
    () => deadStock.reduce((sum, item) => sum + Number(item.value_tied_up), 0),
    [deadStock],
  );

  const loadNearExpiry = useCallback(async () => {
    setNearExpiryLoading(true);
    try {
      setNearExpiry(await getNearExpiryProducts());
    } catch {
      setNearExpiry([]);
    } finally {
      setNearExpiryLoading(false);
    }
  }, []);

  useEffect(() => {
    loadNearExpiry();
  }, [loadNearExpiry]);

  const [inflationPeriod, setInflationPeriod] = useState(() => jalaliPresetRange("this-month-vs-last"));
  const [inflationReport, setInflationReport] = useState<InflationRateReport | null>(null);
  const [inflationLoading, setInflationLoading] = useState(true);

  const loadInflationRate = useCallback(async () => {
    setInflationLoading(true);
    try {
      setInflationReport(
        await getInflationRate({
          period1Start: inflationPeriod.period1Start,
          period1End: inflationPeriod.period1End,
          period2Start: inflationPeriod.period2Start,
          period2End: inflationPeriod.period2End,
        }),
      );
    } catch {
      setInflationReport(null);
    } finally {
      setInflationLoading(false);
    }
  }, [inflationPeriod]);

  useEffect(() => {
    loadInflationRate();
  }, [loadInflationRate]);

  const [cashierPerformance, setCashierPerformance] = useState<CashierPerformanceRow[]>([]);
  const [shifts, setShifts] = useState<CashierShift[]>([]);
  const [cashierLoading, setCashierLoading] = useState(true);
  const [cashierFromDate, setCashierFromDate] = useState(() => {
    const date = new Date();
    date.setDate(date.getDate() - 30);
    return localIsoDate(date);
  });
  const [cashierToDate, setCashierToDate] = useState(() => localIsoDate());

  const loadCashierData = useCallback(async () => {
    setCashierLoading(true);
    try {
      const [performance, shiftHistory] = await Promise.all([
        getCashierPerformance({ fromDate: cashierFromDate, toDate: cashierToDate }),
        getShifts(),
      ]);
      setCashierPerformance(performance);
      setShifts(shiftHistory);
    } catch {
      setCashierPerformance([]);
      setShifts([]);
    } finally {
      setCashierLoading(false);
    }
  }, [cashierFromDate, cashierToDate]);

  useEffect(() => {
    loadCashierData();
  }, [loadCashierData]);

  const emptyState = useMemo(
    () => (
      <div className="empty-state compact">
        <Package size={18} />
        <span>{t("noTransactions")}</span>
      </div>
    ),
    [t],
  );

  const renderMoney = useMemo(
    () => (value: number | string | null | undefined) => formatMoney(Number(value ?? 0), money),
    [money],
  );

  if (viewingSaleId !== null) {
    return <SaleDetailView saleId={viewingSaleId} onBack={() => setViewingSaleId(null)} />;
  }

  return (
    <main className="main-content">
      <header className="page-header">
        <div>
          <p className="eyebrow">{t("reports")}</p>
          <h1>{t("reports")}</h1>
        </div>
      </header>

      {error && <div className="feedback-banner error">{error}</div>}

      <div className="tabs" role="tablist" aria-label={t("reports")}>
        {tabs.map(({ key, label, Icon }) => (
          <button
            key={key}
            className={`tab ${tab === key ? "active" : ""}`}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
          >
            <Icon size={17} strokeWidth={1.8} />
            {t(label)}
          </button>
        ))}
      </div>

      {loading && <div className="empty-state compact">{t("loading")}</div>}

      {!loading && tab === "sales" && (
        <section className="panel report-table-wrap">
          <div className="panel-heading">
            <h2>{t("sales")}</h2>
            <PeriodLabel period={salesPeriod} />
          </div>

          <PeriodSelector value={salesPeriod} onChange={setSalesPeriod} />

          {canSeeNetProfit && netProfitReport && (
            <section className="metric-grid" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))", marginBottom: 16 }}>
              <article className="metric-card">
                <p>{t("grossProfitLabel")}</p>
                <strong className={reportBadgeClass(Number(netProfitReport.gross_profit))}>
                  {renderMoney(Number(netProfitReport.gross_profit))}
                </strong>
              </article>
              <article className="metric-card">
                <p>{t("totalOperatingExpensesLabel")}</p>
                <strong>{renderMoney(Number(netProfitReport.total_operating_expenses))}</strong>
              </article>
              <article className="metric-card" title={t("netProfitTooltip")}>
                <p>
                  {t("netProfitTitle")} <Info size={12} style={{ verticalAlign: "middle" }} />
                </p>
                <strong className={reportBadgeClass(Number(netProfitReport.net_profit))}>
                  {renderMoney(Number(netProfitReport.net_profit))}
                </strong>
              </article>
            </section>
          )}

          <div className="report-table">
            <div className="report-table-row report-cols-5 report-head">
              <span className="report-header-cell">
                <CalendarDays size={14} strokeWidth={1.8} />
                {t("date")}
              </span>
              <span className="report-header-cell">
                <DollarSign size={14} strokeWidth={1.8} />
                {t("total")}
              </span>
              <span className="report-header-cell">
                <BarChart3 size={14} strokeWidth={1.8} />
                {t("transactions")}
              </span>
              <span className="report-header-cell">
                <CircleDollarSign size={14} strokeWidth={1.8} />
                {t("average")}
              </span>
              <span className="report-header-cell">
                <TrendingUp size={14} strokeWidth={1.8} />
                {t("profit")}
              </span>
            </div>
            {dailySales.map((row) => {
              const profit = Number(row.profit);
              const transactionCount = Number(row.transaction_count);
              const totalSales = Number(row.total_sales);
              const averageTicket = Number(row.average_ticket);

              return (
                <div className="report-table-row report-cols-5 animated-line" key={row.date}>
                  <span className="report-date-cell">{isoToJalaliStr(row.date)}</span>
                  <strong>{renderMoney(totalSales)}</strong>
                  <span className="muted-text">{number(transactionCount)}</span>
                  <strong>{renderMoney(averageTicket)}</strong>
                  <strong className={reportBadgeClass(profit)}>{renderMoney(profit)}</strong>
                </div>
              );
            })}
          </div>
          {dailySales.length === 0 && emptyState}

          <div className="panel-heading" style={{ marginTop: 24 }}>
            <h2>{t("recentInvoices")}</h2>
          </div>
          <div className="report-table">
            <div className="report-table-row report-cols-5 report-head">
              <span className="report-header-cell">
                <ReceiptText size={14} strokeWidth={1.8} />
                {t("invoice")}
              </span>
              <span className="report-header-cell">
                <CalendarDays size={14} strokeWidth={1.8} />
                {t("date")}
              </span>
              <span className="report-header-cell">
                <DollarSign size={14} strokeWidth={1.8} />
                {t("total")}
              </span>
              <span className="report-header-cell">
                <TrendingUp size={14} strokeWidth={1.8} />
                {t("invoiceMargin")}
              </span>
              <span />
            </div>
            {invoiceListLoading ? (
              <div className="empty-state compact">{t("loading")}</div>
            ) : invoiceList.length > 0 ? (
              invoiceList.map((sale) => {
                const margin = calculateInvoiceMargin(sale.items);
                return (
                  <button
                    type="button"
                    className="report-table-row report-cols-5 animated-line invoice-history-row"
                    key={sale.id}
                    onClick={() => setViewingSaleId(sale.id)}
                  >
                    <span>{sale.invoice_number}</span>
                    <span className="report-date-cell">{timestampToJalaliStr(sale.created_at)}</span>
                    <strong>{renderMoney(Number(sale.total))}</strong>
                    <span>
                      {margin.marginPct === null ? (
                        "—"
                      ) : (
                        <span className={`margin-value ${getMarginStatus(margin.marginPct)}`}>
                          {formatMarginPct(margin.marginPct, language, number)}
                        </span>
                      )}
                    </span>
                    <span className="text-button">
                      {t("viewDetails")} <ChevronLeft size={14} />
                    </span>
                  </button>
                );
              })
            ) : (
              <div className="empty-state compact">{t("noTransactions")}</div>
            )}
          </div>
        </section>
      )}

      {!loading && tab === "products" && (
        <section className="panel report-table-wrap">
          <div className="panel-heading">
            <h2>{t("products")}</h2>
            <span className="subtle-chip">{t("topSelling")}</span>
          </div>
          <div className="report-table">
            <div className="report-table-row report-cols-5 report-head">
              <span className="report-header-cell">
                <Package size={14} strokeWidth={1.8} />
                {t("product")}
              </span>
              <span className="report-header-cell">
                <BarChart3 size={14} strokeWidth={1.8} />
                {t("quantity")}
              </span>
              <span className="report-header-cell">
                <DollarSign size={14} strokeWidth={1.8} />
                {t("total")}
              </span>
              <span className="report-header-cell">
                <TrendingUp size={14} strokeWidth={1.8} />
                {t("marginPct")}
              </span>
              <span className="report-header-cell">
                <TrendingUp size={14} strokeWidth={1.8} />
                {t("totalProfit")}
              </span>
            </div>
            {topProducts.map((product) => {
              const totalRevenue = Number(product.total_revenue);
              const totalProfit = Number(product.total_profit);
              const marginPct = calculateMarginPct(totalRevenue, totalRevenue - totalProfit);
              return (
                <div className="report-table-row report-cols-5 animated-line" key={product.product_id}>
                  <strong>{product.product_name}</strong>
                  <span className="muted-text">{number(Number(product.total_quantity))}</span>
                  <strong>{renderMoney(totalRevenue)}</strong>
                  <span>
                    {marginPct === null ? (
                      "—"
                    ) : (
                      <span className={`margin-value ${getMarginStatus(marginPct)}`}>
                        {formatMarginPct(marginPct, language, number)}
                      </span>
                    )}
                  </span>
                  <strong className={reportBadgeClass(totalProfit)}>{renderMoney(totalProfit)}</strong>
                </div>
              );
            })}
          </div>
          {topProducts.length === 0 && emptyState}
        </section>
      )}

      {!loading && tab === "stock" && (
        <>
          <section className="panel report-table-wrap">
            <div className="panel-heading">
              <h2>{t("inventory")}</h2>
              <span className="subtle-chip">{t("stockValue")}</span>
            </div>
            <div className="report-table">
            <div className="report-table-row report-cols-5 report-head">
                <span className="report-header-cell">
                  <Package size={14} strokeWidth={1.8} />
                  {t("product")}
                </span>
                <span className="report-header-cell">
                  <Boxes size={14} strokeWidth={1.8} />
                  {t("stock")}
                </span>
                <span className="report-header-cell">
                  <DollarSign size={14} strokeWidth={1.8} />
                  {t("stockValue")}
                </span>
                <span className="report-header-cell">
                  <TrendingUp size={14} strokeWidth={1.8} />
                  {t("marginPct")}
                </span>
                <span className="report-header-cell">
                  <TrendingUp size={14} strokeWidth={1.8} />
                  {t("potentialProfit")}
                </span>
              </div>
              {inventory.map((item) => {
                const stockValue = Number(item.total_stock_value);
                const potentialProfit = item.potential_profit === null ? 0 : Number(item.potential_profit);
                const marginPct = calculateMarginPct(Number(item.sale_price), Number(item.purchase_price));

                return (
                <div className="report-table-row report-cols-5 animated-line" key={item.product_id}>
                    <strong>{item.product_name}</strong>
                    <span className="muted-text">{number(Number(item.stock_quantity))}</span>
                    <strong className="metric-badge metric-badge-neutral">
                      {renderMoney(stockValue)}
                    </strong>
                    <span>
                      {marginPct === null ? (
                        "—"
                      ) : (
                        <span className={`margin-value ${getMarginStatus(marginPct)}`}>
                          {formatMarginPct(marginPct, language, number)}
                        </span>
                      )}
                    </span>
                    <strong className={reportBadgeClass(potentialProfit)}>
                      {item.potential_profit === null ? "—" : renderMoney(potentialProfit)}
                    </strong>
                  </div>
                );
              })}
            </div>
            {inventory.length === 0 && (
              <div className="empty-state compact">{t("noTransactions")}</div>
            )}
          </section>

          <section className="panel report-table-wrap" style={{ marginTop: 16 }}>
            <div className="panel-heading">
              <h2>{t("lowStock")}</h2>
            </div>
            <div className="report-table">
            <div className="report-table-row report-cols-3 report-head">
                <span className="report-header-cell">
                  <Package size={14} strokeWidth={1.8} />
                  {t("product")}
                </span>
                <span className="report-header-cell">
                  <Boxes size={14} strokeWidth={1.8} />
                  {t("stock")}
                </span>
                <span className="report-header-cell">
                  <Boxes size={14} strokeWidth={1.8} />
                  {t("lowStock")}
                </span>
              </div>
              {lowStock.length > 0 ? (
                lowStock.map((item) => (
                  <div className="report-table-row report-cols-3 animated-line" key={item.product_id}>
                    <strong>{item.product_name}</strong>
                    <strong>{number(Number(item.stock_quantity))}</strong>
                    <strong className="quantity-negative">
                      {number(Number(item.low_stock_threshold))}
                    </strong>
                  </div>
                ))
              ) : (
                <div className="empty-state compact">{t("noData")}</div>
              )}
            </div>
          </section>
        </>
      )}

      {!loading && tab === "dead-stock" && (
        <section className="panel report-table-wrap">
          <div className="panel-heading">
            <div>
              <h2>{t("deadStockTitle")}</h2>
              <span className="subtle-chip" style={{ marginTop: 6, display: "inline-block" }}>
                {t("deadStockSubtitle")}
              </span>
            </div>
            <label className="field" style={{ margin: 0 }}>
              <span>{t("deadStockLookback")}</span>
              <select
                value={deadStockLookback}
                onChange={(event) => setDeadStockLookback(Number(event.target.value) as 30 | 60 | 90)}
              >
                <option value={30}>{t("last30Days")}</option>
                <option value={60}>{t("last60Days")}</option>
                <option value={90}>{t("last90Days")}</option>
              </select>
            </label>
          </div>

          {!deadStockLoading && deadStock.length > 0 && (
            <div className="report-meta-row">
              <strong className="metric-badge metric-badge-danger">
                {t("totalValueTiedUp")}: {renderMoney(totalValueTiedUp)}
              </strong>
            </div>
          )}

          <div className="report-table">
            <div className="report-table-row report-cols-5 report-head">
              <span className="report-header-cell">
                <Moon size={14} strokeWidth={1.8} />
                {t("product")}
              </span>
              <span className="report-header-cell">
                <Boxes size={14} strokeWidth={1.8} />
                {t("stock")}
              </span>
              <span className="report-header-cell">
                <Clock size={14} strokeWidth={1.8} />
                {t("daysSinceLastSale")}
              </span>
              <span className="report-header-cell">
                <DollarSign size={14} strokeWidth={1.8} />
                {t("valueTiedUp")}
              </span>
              <span className="report-header-cell">
                <Package size={14} strokeWidth={1.8} />
                {t("category")}
              </span>
            </div>
            {deadStockLoading ? (
              <div className="empty-state compact">{t("loading")}</div>
            ) : deadStock.length > 0 ? (
              deadStock.map((item) => (
                <div className="report-table-row report-cols-5 animated-line" key={item.product_id}>
                  <strong>{item.product_name}</strong>
                  <span className="muted-text">{number(Number(item.stock_quantity))}</span>
                  <span>
                    {item.days_since_last_sale === null ? t("neverSold") : number(item.days_since_last_sale)}
                  </span>
                  <strong className="metric-badge metric-badge-danger">
                    {renderMoney(Number(item.value_tied_up))}
                  </strong>
                  <span className="muted-text">{item.category_name ?? t("noCategory")}</span>
                </div>
              ))
            ) : (
              <div className="empty-state compact">{t("noDeadStock")}</div>
            )}
          </div>
        </section>
      )}

      {!loading && tab === "near-expiry" && (
        <section className="panel report-table-wrap">
          <div className="panel-heading">
            <div>
              <h2>{t("nearExpiryTitle")}</h2>
            </div>
            {onNavigate && (
              <button
                type="button"
                className="secondary-button"
                onClick={() => {
                  // Same hand-off key the Dashboard widget uses — Products.tsx
                  // reads it once on mount to open pre-filtered.
                  localStorage.setItem("marketa-products-filter", "expiry");
                  onNavigate("products");
                }}
              >
                {t("viewAll")}
              </button>
            )}
          </div>

          <div className="report-table">
            <div className="report-table-row report-cols-4 report-head">
              <span className="report-header-cell">
                <CalendarClock size={14} strokeWidth={1.8} />
                {t("product")}
              </span>
              <span className="report-header-cell">
                <Boxes size={14} strokeWidth={1.8} />
                {t("stock")}
              </span>
              <span className="report-header-cell">
                <Clock size={14} strokeWidth={1.8} />
                {t("expiryDateColumn")}
              </span>
              <span className="report-header-cell" />
            </div>
            {nearExpiryLoading ? (
              <div className="empty-state compact">{t("loading")}</div>
            ) : nearExpiry.length > 0 ? (
              nearExpiry.map((item) => (
                <div className="report-table-row report-cols-4 animated-line" key={item.product_id}>
                  <strong>{item.product_name}</strong>
                  <span className="muted-text">{number(Number(item.stock_quantity))}</span>
                  <span className="muted-text">{isoToJalaliStr(item.expiration_date)}</span>
                  <span className={`expiry-status-badge ${item.status}`}>
                    {item.status === "expired"
                      ? t("alreadyExpiredLabel")
                      : t("daysRemainingLabel").replace("{days}", number(item.days_until_expiry))}
                  </span>
                </div>
              ))
            ) : (
              <div className="empty-state compact">{t("systemOnline")}</div>
            )}
          </div>
        </section>
      )}

      {!loading && tab === "inflation-rate" && (
        <section className="panel report-table-wrap">
          <div className="panel-heading">
            <div>
              <h2>{t("inflationRateTitle")}</h2>
              <span className="subtle-chip" style={{ marginTop: 6, display: "inline-block" }}>
                {t("inflationRateSubtitle")}
              </span>
            </div>
          </div>

          <div className="date-range-filter" style={{ flexWrap: "wrap", rowGap: 12 }}>
            <div>
              <small className="field-hint">{t("periodOne")}</small>
              <div className="date-range-filter">
                <JalaliDatePicker
                  value={inflationPeriod.period1Start}
                  onChange={(value) => setInflationPeriod((prev) => ({ ...prev, period1Start: value }))}
                />
                <span>—</span>
                <JalaliDatePicker
                  value={inflationPeriod.period1End}
                  onChange={(value) => setInflationPeriod((prev) => ({ ...prev, period1End: value }))}
                />
              </div>
            </div>
            <div>
              <small className="field-hint">{t("periodTwo")}</small>
              <div className="date-range-filter">
                <JalaliDatePicker
                  value={inflationPeriod.period2Start}
                  onChange={(value) => setInflationPeriod((prev) => ({ ...prev, period2Start: value }))}
                />
                <span>—</span>
                <JalaliDatePicker
                  value={inflationPeriod.period2End}
                  onChange={(value) => setInflationPeriod((prev) => ({ ...prev, period2End: value }))}
                />
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                className="secondary-button"
                onClick={() => setInflationPeriod(jalaliPresetRange("this-month-vs-last"))}
              >
                {t("presetThisMonthVsLast")}
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={() => setInflationPeriod(jalaliPresetRange("this-year-vs-last"))}
              >
                {t("presetThisYearVsLast")}
              </button>
            </div>
          </div>

          {inflationLoading ? (
            <div className="empty-state compact">{t("loading")}</div>
          ) : !inflationReport || inflationReport.insufficient_data ? (
            <div className="empty-state compact">{t("insufficientInflationData")}</div>
          ) : (
            <>
              {inflationReport.diagnosis && (
                <div className="report-meta-row">
                  <p style={{ margin: 0 }}>{inflationReport.diagnosis.summary_sentence}</p>
                </div>
              )}

              <details className="inflation-glossary" style={{ marginTop: 12 }}>
                <summary>{t("inflationGlossaryTitle")}</summary>
                <ul>
                  <li>{t("glossaryCostInflation")}</li>
                  <li>{t("glossaryPriceInflation")}</li>
                  <li>{t("glossaryVolumeIndex")}</li>
                  <li>{t("glossaryRealProfitIndex")}</li>
                  <li>{t("glossaryRevenueImpact")}</li>
                  <li>{t("glossaryDiagnosisHealthy")}</li>
                  <li>{t("glossaryDiagnosisStagflation")}</li>
                  <li>{t("glossaryDiagnosisCompetitive")}</li>
                  <li>{t("glossaryDiagnosisRealRecession")}</li>
                </ul>
              </details>

              <section className="metric-grid" style={{ marginTop: 12 }}>
                <article className="metric-card">
                  <p>{t("costInflation")}</p>
                  <strong className={reportBadgeClass(Number(inflationReport.cost_inflation_pct))}>
                    {inflationReport.cost_inflation_pct === null
                      ? "—"
                      : formatSignedPct(Number(inflationReport.cost_inflation_pct), number)}
                  </strong>
                </article>
                <article className="metric-card">
                  <p>{t("priceInflation")}</p>
                  <strong className={reportBadgeClass(Number(inflationReport.price_inflation_pct))}>
                    {formatSignedPct(Number(inflationReport.price_inflation_pct), number)}
                  </strong>
                </article>
                <article className="metric-card">
                  <p>{t("volumeIndex")}</p>
                  <strong className={reportBadgeClass(Number(inflationReport.volume_index_pct))}>
                    {formatSignedPct(Number(inflationReport.volume_index_pct), number)}
                  </strong>
                  <small className="metric-hint">{t("volumeIndexHint")}</small>
                </article>
                <article className="metric-card">
                  <p>{t("realProfitIndex")}</p>
                  <strong className={reportBadgeClass(Number(inflationReport.real_profit_index_pct))}>
                    {inflationReport.real_profit_index_pct === null
                      ? "—"
                      : formatSignedPct(Number(inflationReport.real_profit_index_pct), number)}
                  </strong>
                </article>
              </section>

              <div className="panel-heading" style={{ marginTop: 24 }}>
                <h2>{t("revenueImpactTitle")}</h2>
              </div>
              <section className="metric-grid" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
                <article className="metric-card">
                  <p>
                    {t("nominalRevenue")} — {t("periodOne")}
                  </p>
                  <strong>{renderMoney(Number(inflationReport.revenue_impact.nominal_revenue_p1))}</strong>
                </article>
                <article className="metric-card">
                  <p>
                    {t("nominalRevenue")} — {t("periodTwo")}
                  </p>
                  <strong>{renderMoney(Number(inflationReport.revenue_impact.nominal_revenue_p2))}</strong>
                  {inflationReport.revenue_impact.nominal_growth_pct !== null && (
                    <small className={reportBadgeClass(Number(inflationReport.revenue_impact.nominal_growth_pct))}>
                      {formatSignedPct(Number(inflationReport.revenue_impact.nominal_growth_pct), number)}{" "}
                      {t("nominalGrowth")}
                    </small>
                  )}
                </article>
                <article className="metric-card">
                  <p>{t("realRevenue")}</p>
                  <strong>
                    {inflationReport.revenue_impact.real_revenue_p2 === null
                      ? "—"
                      : renderMoney(Number(inflationReport.revenue_impact.real_revenue_p2))}
                  </strong>
                  {inflationReport.revenue_impact.real_growth_pct !== null && (
                    <small className={reportBadgeClass(Number(inflationReport.revenue_impact.real_growth_pct))}>
                      {formatSignedPct(Number(inflationReport.revenue_impact.real_growth_pct), number)} {t("realGrowth")}
                    </small>
                  )}
                </article>
              </section>

              <div className="panel-heading" style={{ marginTop: 24 }}>
                <h2>{t("categoryBreakdownTitle")}</h2>
              </div>
              <div className="report-table report-table-wrap">
                <div className="report-table-row report-cols-5 report-head">
                  <span className="report-header-cell">{t("category")}</span>
                  <span className="report-header-cell">{t("costInflation")}</span>
                  <span className="report-header-cell">{t("priceInflation")}</span>
                  <span className="report-header-cell">{t("volumeIndex")}</span>
                  <span className="report-header-cell" />
                </div>
                {inflationReport.by_category.map((row) => (
                  <div className="report-table-row report-cols-5 animated-line" key={row.category_id ?? "none"}>
                    <strong>{row.category_name}</strong>
                    {row.insufficient_data ? (
                      <span className="muted-text" style={{ gridColumn: "span 3" }}>
                        {t("insufficientInflationData")}
                      </span>
                    ) : (
                      <>
                        <span className={reportBadgeClass(Number(row.cost_inflation_pct))}>
                          {row.cost_inflation_pct === null ? "—" : formatSignedPct(Number(row.cost_inflation_pct), number)}
                        </span>
                        <span className={reportBadgeClass(Number(row.price_inflation_pct))}>
                          {formatSignedPct(Number(row.price_inflation_pct), number)}
                        </span>
                        <span className={reportBadgeClass(Number(row.volume_index_pct))}>
                          {formatSignedPct(Number(row.volume_index_pct), number)}
                        </span>
                      </>
                    )}
                    <span className="muted-text">{row.diagnosis?.title ?? "—"}</span>
                  </div>
                ))}
              </div>

              <div className="inflation-stacked-tables" style={{ marginTop: 24 }}>
                <div>
                  <div className="panel-heading">
                    <h2>{t("topPriceIncreasesTitle")}</h2>
                  </div>
                  <div className="report-table report-table-wrap">
                    <div className="report-table-row report-cols-3 report-head">
                      <span className="report-header-cell">{t("product")}</span>
                      <span className="report-header-cell">{t("priceInflation")}</span>
                      <span className="report-header-cell" />
                    </div>
                    {inflationReport.top_price_increases.length > 0 ? (
                      inflationReport.top_price_increases.map((row) => (
                        <div className="report-table-row report-cols-3 animated-line" key={row.product_id}>
                          <strong>{row.product_name}</strong>
                          <span className="muted-text" style={{ justifySelf: "start" }}>
                            {/* money() rather than number() + a fixed "تومان":
                                these are prices, so they have to follow the
                                toman/rial preference like every other figure. */}
                            <span style={{ direction: "ltr", unicodeBidi: "isolate" }}>
                              {money(Number(row.price_period1))} → {money(Number(row.price_period2))}
                            </span>
                          </span>
                          <span className={reportBadgeClass(Number(row.pct_change))}>
                            {formatSignedPct(Number(row.pct_change), number)}
                          </span>
                        </div>
                      ))
                    ) : (
                      <div className="empty-state compact">{t("noData")}</div>
                    )}
                  </div>
                </div>
                <div style={{ marginTop: 24 }}>
                  <div className="panel-heading">
                    <h2>{t("topVolumeDeclinersTitle")}</h2>
                  </div>
                  <div className="report-table report-table-wrap">
                    <div className="report-table-row report-cols-3 report-head">
                      <span className="report-header-cell">{t("product")}</span>
                      <span className="report-header-cell">{t("quantity")}</span>
                      <span className="report-header-cell" />
                    </div>
                    {inflationReport.top_volume_decliners.length > 0 ? (
                      inflationReport.top_volume_decliners.map((row) => (
                        <div className="report-table-row report-cols-3 animated-line" key={row.product_id}>
                          <strong>{row.product_name}</strong>
                          <span className="muted-text" style={{ direction: "ltr", justifySelf: "start" }}>
                            {number(Number(row.quantity_period1))} → {number(Number(row.quantity_period2))}
                          </span>
                          <span className={reportBadgeClass(Number(row.pct_change))}>
                            {formatSignedPct(Number(row.pct_change), number)}
                          </span>
                        </div>
                      ))
                    ) : (
                      <div className="empty-state compact">{t("noData")}</div>
                    )}
                  </div>
                </div>
              </div>
            </>
          )}

          <p className="muted-text" style={{ marginTop: 16, fontSize: 12 }}>
            {t("inflationLimitationNote")}
          </p>
        </section>
      )}

      {tab === "cashiers" && (
        <>
          <section className="panel report-table-wrap">
            <div className="panel-heading">
              <div>
                <h2>{t("cashierPerformance")}</h2>
                <span className="subtle-chip" style={{ marginTop: 6, display: "inline-block" }}>
                  {t("cashierPerformanceSubtitle")}
                </span>
              </div>
              <div className="date-range-filter">
                <JalaliDatePicker value={cashierFromDate} onChange={setCashierFromDate} />
                <span>—</span>
                <JalaliDatePicker value={cashierToDate} onChange={setCashierToDate} />
              </div>
            </div>

            <div className="report-table">
              <div className="report-table-row cashier-perf-columns report-head">
                <span className="report-header-cell">
                  <UserRound size={14} strokeWidth={1.8} />
                  {t("cashier")}
                </span>
                <span className="report-header-cell">
                  <BarChart3 size={14} strokeWidth={1.8} />
                  {t("invoiceCount")}
                </span>
                <span className="report-header-cell">
                  <DollarSign size={14} strokeWidth={1.8} />
                  {t("total")}
                </span>
                <span className="report-header-cell">
                  <CircleDollarSign size={14} strokeWidth={1.8} />
                  {t("average")}
                </span>
                <span className="report-header-cell">{t("discount")}</span>
                <span className="report-header-cell">{t("cash")}</span>
                <span className="report-header-cell">{t("card")}</span>
                {/* The reason this column exists: money transferred straight
                    to the owner's card never passes through the till or the
                    POS terminal, so the only way to catch a cashier who gave
                    out their own card number is to total it per cashier and
                    compare against what actually arrived in the bank. */}
                <span className="report-header-cell">{t("cardToCard")}</span>
                <span className="report-header-cell">{t("credit")}</span>
                <span className="report-header-cell">{t("editedCount")}</span>
                <span className="report-header-cell">{t("heldCount")}</span>
                <span className="report-header-cell">{t("discardedCount")}</span>
              </div>
              {cashierLoading ? (
                <div className="empty-state compact">{t("loading")}</div>
              ) : cashierPerformance.length > 0 ? (
                cashierPerformance.map((row) => (
                  <div className="report-table-row cashier-perf-columns animated-line" key={row.cashier_id}>
                    <strong>{row.cashier_name}</strong>
                    <span className="muted-text">{number(row.invoice_count)}</span>
                    <strong>{renderMoney(Number(row.total_sales))}</strong>
                    <span>{renderMoney(Number(row.average_ticket))}</span>
                    <span className="muted-text">{renderMoney(Number(row.total_discount))}</span>
                    <span className="muted-text">{renderMoney(Number(row.payment_method_breakdown.cash ?? 0))}</span>
                    <span className="muted-text">{renderMoney(Number(row.payment_method_breakdown.card ?? 0))}</span>
                    <span className="muted-text">
                      {renderMoney(Number(row.payment_method_breakdown.card_to_card ?? 0))}
                    </span>
                    <span className="muted-text">{renderMoney(Number(row.payment_method_breakdown.credit ?? 0))}</span>
                    <span className="muted-text">{number(row.edited_count)}</span>
                    <span className="muted-text">{number(row.held_count)}</span>
                    <span className="muted-text">{number(row.discarded_count)}</span>
                  </div>
                ))
              ) : (
                <div className="empty-state compact">{t("noData")}</div>
              )}
            </div>
          </section>

          <section className="panel report-table-wrap" style={{ marginTop: 16 }}>
            <div className="panel-heading">
              <h2>{t("shiftHistory")}</h2>
            </div>
            <div className="report-table">
              <div className="report-table-row shift-history-columns report-head">
                <span className="report-header-cell">
                  <UserRound size={14} strokeWidth={1.8} />
                  {t("cashier")}
                </span>
                <span className="report-header-cell">
                  <Clock size={14} strokeWidth={1.8} />
                  {t("openedAt")}
                </span>
                <span className="report-header-cell">{t("closedAt")}</span>
                <span className="report-header-cell">{t("openingCash")}</span>
                <span className="report-header-cell">{t("countedCash")}</span>
                <span className="report-header-cell">{t("difference")}</span>
              </div>
              {cashierLoading ? (
                <div className="empty-state compact">{t("loading")}</div>
              ) : shifts.length > 0 ? (
                shifts.map((shift) => {
                  const difference = shift.difference === null ? null : Number(shift.difference);
                  return (
                    <div className="report-table-row shift-history-columns animated-line" key={shift.id}>
                      <strong>{shift.cashier_name}</strong>
                      <span className="muted-text">{timestampToJalaliStr(shift.opened_at)} {timestampToLocalTime(shift.opened_at)}</span>
                      <span className="muted-text">
                        {shift.closed_at
                          ? `${timestampToJalaliStr(shift.closed_at)} ${timestampToLocalTime(shift.closed_at)}`
                          : t("openShiftBadge")}
                      </span>
                      <span>{renderMoney(Number(shift.opening_cash))}</span>
                      <span>{shift.closing_cash === null ? "—" : renderMoney(Number(shift.closing_cash))}</span>
                      <strong className={difference === null ? "" : reportBadgeClass(difference)}>
                        {difference === null ? "—" : renderMoney(difference)}
                      </strong>
                    </div>
                  );
                })
              ) : (
                <div className="empty-state compact">{t("noData")}</div>
              )}
            </div>
          </section>
        </>
      )}

      {!loading && tab === "balances" && (
        <>
          <section className="panel report-table-wrap">
            <div className="panel-heading">
              <h2>{t("customers")}</h2>
              <span className="subtle-chip">{t("receivables")}</span>
            </div>
            <div className="report-table">
            <div className="report-table-row report-cols-3 report-head">
                <span className="report-header-cell">
                  <UsersRound size={14} strokeWidth={1.8} />
                  {t("fullName")}
                </span>
                <span className="report-header-cell">
                  <Wallet size={14} strokeWidth={1.8} />
                  {t("balance")}
                </span>
                <span className="report-header-cell">
                  <CircleDollarSign size={14} strokeWidth={1.8} />
                  {t("creditLimit")}
                </span>
              </div>
              {customerBals.map((customer) => (
                <div className="report-table-row report-cols-3 animated-line" key={customer.customer_id}>
                  <strong>{customer.customer_name}</strong>
                  <strong className="quantity-negative">
                    {renderMoney(Number(customer.balance))}
                  </strong>
                  <span>{renderMoney(Number(customer.credit_limit))}</span>
                </div>
              ))}
              {customerBals.length === 0 && (
                <div className="empty-state compact">{t("noCustomers")}</div>
              )}
            </div>
          </section>

          <section className="panel report-table-wrap">
            <div className="panel-heading">
              <h2>{t("suppliers")}</h2>
              <span className="subtle-chip">{t("payables")}</span>
            </div>
            <div className="report-table">
            <div className="report-table-row report-cols-3 report-head">
                <span className="report-header-cell">
                  <UsersRound size={14} strokeWidth={1.8} />
                  {t("supplierName")}
                </span>
                <span className="report-header-cell">
                  <Wallet size={14} strokeWidth={1.8} />
                  {t("balance")}
                </span>
                <span className="report-header-cell">
                  <CircleDollarSign size={14} strokeWidth={1.8} />
                  {t("creditLimit")}
                </span>
              </div>
              {supplierBals.map((supplier) => (
                <div className="report-table-row report-cols-3 animated-line" key={supplier.supplier_id}>
                  <strong>{supplier.supplier_name}</strong>
                  <strong className="quantity-negative">
                    {renderMoney(Number(supplier.balance))}
                  </strong>
                  <span>{renderMoney(Number(supplier.credit_limit))}</span>
                </div>
              ))}
              {supplierBals.length === 0 && (
                <div className="empty-state compact">{t("noSuppliers")}</div>
              )}
            </div>
          </section>
        </>
      )}

      {tab === "loyalty" && (
        <section className="panel report-table-wrap">
          <div className="panel-heading">
            <div>
              <h2>{t("loyaltyRedemptions")}</h2>
              <span className="subtle-chip" style={{ marginTop: 6, display: "inline-block" }}>
                {t("loyaltyRedemptionsSubtitle")}
              </span>
            </div>
          </div>
          <div className="report-table">
            <div className="report-table-row report-cols-5 report-head">
              <span className="report-header-cell">
                <UsersRound size={14} strokeWidth={1.8} />
                {t("fullName")}
              </span>
              <span className="report-header-cell">
                <ReceiptText size={14} strokeWidth={1.8} />
                {t("invoice")}
              </span>
              <span className="report-header-cell">
                <Package size={14} strokeWidth={1.8} />
                {t("product")}
              </span>
              <span className="report-header-cell">
                <DollarSign size={14} strokeWidth={1.8} />
                {t("discount")}
              </span>
              <span className="report-header-cell">
                <Gift size={14} strokeWidth={1.8} />
                {t("loyaltyPoints")}
              </span>
            </div>
            {redemptionLoading ? (
              <div className="empty-state compact">{t("loading")}</div>
            ) : redemptionRows.length > 0 ? (
              redemptionRows.map((row) => (
                <div className="report-table-row report-cols-5 animated-line" key={row.payment_id}>
                  <strong>{row.customer_name}</strong>
                  <span>{row.invoice_number ?? "—"}</span>
                  <span className="muted-text">{row.product_names.join("، ")}</span>
                  <strong className="metric-badge metric-badge-danger">{renderMoney(Number(row.discount_value))}</strong>
                  <span className="muted-text">{number(row.points_used)}</span>
                </div>
              ))
            ) : (
              <div className="empty-state compact">{t("noLoyaltyRedemptions")}</div>
            )}
          </div>
        </section>
      )}
    </main>
  );
}
