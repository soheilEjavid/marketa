import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  Boxes,
  CalendarDays,
  CheckCircle2,
  ChevronLeft,
  CircleDollarSign,
  Clock,
  DollarSign,
  Gift,
  Moon,
  Package,
  ReceiptText,
  TrendingUp,
  UserRound,
  Wallet,
  UsersRound,
} from "lucide-react";

import {
  getCashierPerformance,
  getLoyaltyRedemptions,
  getOutstandingConsignment,
  getSalesPage,
  getShifts,
  request,
  settleConsignmentItem,
} from "../api";
import { JalaliDatePicker } from "../components/JalaliDatePicker";
import { SaleDetailView } from "../components/SaleDetailView";
import { useI18n } from "../i18n";
import { calculateInvoiceMargin, calculateMarginPct, formatMarginPct, getMarginStatus } from "../lib/margin";
import { isoToJalaliStr } from "../utils/jalali";
import type {
  CashierPerformanceRow,
  CashierShift,
  DeadStockRow,
  LoyaltyRedemptionRow,
  OutstandingConsignmentRow,
  Sale,
} from "../types";

type ReportTab = "sales" | "products" | "stock" | "dead-stock" | "cashiers" | "balances" | "consignment" | "loyalty";

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

const tabs: ReportTabDefinition[] = [
  { key: "sales", label: "sales", Icon: BarChart3 },
  { key: "products", label: "products", Icon: TrendingUp },
  { key: "stock", label: "inventory", Icon: ReceiptText },
  { key: "dead-stock", label: "deadStockTitle", Icon: Moon },
  { key: "cashiers", label: "cashierPerformance", Icon: UserRound },
  { key: "balances", label: "balances", Icon: UsersRound },
  { key: "consignment", label: "consignmentGoods", Icon: Package },
  { key: "loyalty", label: "loyaltyRedemptions", Icon: Gift },
];

export function Reports() {
  const { money, number, t, language } = useI18n();

  const [tab, setTab] = useState<ReportTab>("sales");
  const [dailySales, setDailySales] = useState<DailySalesRow[]>([]);
  const [topProducts, setTopProducts] = useState<TopProduct[]>([]);
  const [lowStock, setLowStock] = useState<LowStockItem[]>([]);
  const [inventory, setInventory] = useState<InvItem[]>([]);
  const [customerBals, setCustomerBals] = useState<BalItem[]>([]);
  const [supplierBals, setSupplierBals] = useState<BalItem[]>([]);
  const [deadStock, setDeadStock] = useState<DeadStockRow[]>([]);
  const [deadStockLookback, setDeadStockLookback] = useState<30 | 60 | 90>(30);
  const [deadStockLoading, setDeadStockLoading] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [invoiceList, setInvoiceList] = useState<Sale[]>([]);
  const [invoiceListLoading, setInvoiceListLoading] = useState(true);
  const [viewingSaleId, setViewingSaleId] = useState<number | null>(null);
  const [consignmentRows, setConsignmentRows] = useState<OutstandingConsignmentRow[]>([]);
  const [consignmentLoading, setConsignmentLoading] = useState(true);
  const [settlingItemId, setSettlingItemId] = useState<number | null>(null);
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
        request<DailySalesRow[]>(`${base}/daily-sales`),
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
  }, [t]);

  useEffect(() => {
    loadData();
  }, [loadData]);

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

  const loadConsignment = useCallback(async () => {
    setConsignmentLoading(true);
    try {
      const rows = await getOutstandingConsignment();
      setConsignmentRows(rows);
    } catch {
      setConsignmentRows([]);
    } finally {
      setConsignmentLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConsignment();
  }, [loadConsignment]);

  async function handleSettleConsignment(itemId: number) {
    setSettlingItemId(itemId);
    try {
      await settleConsignmentItem(itemId);
      await loadConsignment();
    } catch {
      setError(t("apiError"));
    } finally {
      setSettlingItemId(null);
    }
  }

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

  const [cashierPerformance, setCashierPerformance] = useState<CashierPerformanceRow[]>([]);
  const [shifts, setShifts] = useState<CashierShift[]>([]);
  const [cashierLoading, setCashierLoading] = useState(true);
  const [cashierFromDate, setCashierFromDate] = useState(() => {
    const date = new Date();
    date.setDate(date.getDate() - 30);
    return date.toISOString().slice(0, 10);
  });
  const [cashierToDate, setCashierToDate] = useState(() => new Date().toISOString().slice(0, 10));

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
            <span className="subtle-chip">{t("salesTrend")}</span>
          </div>
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
                    <span className="report-date-cell">{isoToJalaliStr(sale.created_at.slice(0, 10))}</span>
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
                      <span className="muted-text">{isoToJalaliStr(shift.opened_at.slice(0, 10))} {shift.opened_at.slice(11, 16)}</span>
                      <span className="muted-text">
                        {shift.closed_at
                          ? `${isoToJalaliStr(shift.closed_at.slice(0, 10))} ${shift.closed_at.slice(11, 16)}`
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

      {tab === "consignment" && (
        <section className="panel report-table-wrap">
          <div className="panel-heading">
            <div>
              <h2>{t("consignmentGoods")}</h2>
              <span className="subtle-chip" style={{ marginTop: 6, display: "inline-block" }}>
                {t("consignmentGoodsSubtitle")}
              </span>
            </div>
          </div>

          <div className="report-table">
            <div className="report-table-row consignment-report-columns report-head">
              <span className="report-header-cell">
                <UsersRound size={14} strokeWidth={1.8} />
                {t("supplier")}
              </span>
              <span className="report-header-cell">
                <Package size={14} strokeWidth={1.8} />
                {t("product")}
              </span>
              <span className="report-header-cell">
                <Boxes size={14} strokeWidth={1.8} />
                {t("quantity")}
              </span>
              <span className="report-header-cell">
                <DollarSign size={14} strokeWidth={1.8} />
                {t("value")}
              </span>
              <span className="report-header-cell">
                <CalendarDays size={14} strokeWidth={1.8} />
                {t("dateReceived")}
              </span>
              <span />
            </div>
            {consignmentLoading ? (
              <div className="empty-state compact">{t("loading")}</div>
            ) : consignmentRows.length > 0 ? (
              consignmentRows.map((row) => (
                <div className="report-table-row consignment-report-columns animated-line" key={row.purchase_item_id}>
                  <strong>{row.supplier_name ?? "—"}</strong>
                  <span>
                    {row.product_name}
                    <br />
                    <span className="muted-text" style={{ fontSize: 11 }}>{row.invoice_number}</span>
                  </span>
                  <span className="muted-text">{number(Number(row.quantity))}</span>
                  <strong>{renderMoney(Number(row.value))}</strong>
                  <span className="report-date-cell">{isoToJalaliStr(row.received_at.slice(0, 10))}</span>
                  <button
                    type="button"
                    className="text-button"
                    disabled={settlingItemId === row.purchase_item_id}
                    onClick={() => handleSettleConsignment(row.purchase_item_id)}
                  >
                    <CheckCircle2 size={14} /> {t("markSettled")}
                  </button>
                </div>
              ))
            ) : (
              <div className="empty-state compact">{t("noOutstandingConsignment")}</div>
            )}
          </div>
        </section>
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
