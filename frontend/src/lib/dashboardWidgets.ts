export type WidgetId =
  | "kpi-today-sales"
  | "kpi-receivables"
  | "kpi-active-products"
  | "kpi-low-stock"
  | "chart-sales-trend"
  | "chart-profit-trend"
  | "list-low-stock"
  | "list-top-debtors"
  | "list-recent-activity"
  | "chart-sales-comparison"
  | "chart-payment-methods"
  | "chart-top-products"
  | "check-calendar"
  | "check-totals";

export type WidgetDefinition = {
  id: WidgetId;
  labelKey: string;
};

/** All toggleable dashboard widgets. Order here is the order shown in the customize panel. */
export const DASHBOARD_WIDGETS: WidgetDefinition[] = [
  { id: "kpi-today-sales", labelKey: "todaySales" },
  { id: "kpi-receivables", labelKey: "receivables" },
  { id: "kpi-active-products", labelKey: "activeProducts" },
  { id: "kpi-low-stock", labelKey: "lowStock" },
  { id: "chart-sales-trend", labelKey: "salesTrend" },
  { id: "chart-profit-trend", labelKey: "profitTrend" },
  { id: "list-low-stock", labelKey: "inventoryAttention" },
  { id: "list-top-debtors", labelKey: "topDebtors" },
  { id: "list-recent-activity", labelKey: "latestTransactions" },
  { id: "chart-sales-comparison", labelKey: "salesComparisonTitle" },
  { id: "chart-payment-methods", labelKey: "paymentMethodBreakdownTitle" },
  { id: "chart-top-products", labelKey: "topProductsChartTitle" },
  { id: "check-calendar", labelKey: "checkCalendarTitle" },
  { id: "check-totals", labelKey: "checkTotalsWidgetTitle" },
];

const STORAGE_KEY = "marketa-dashboard-widgets";

function defaultVisibility(): Record<WidgetId, boolean> {
  return Object.fromEntries(DASHBOARD_WIDGETS.map((widget) => [widget.id, true])) as Record<
    WidgetId,
    boolean
  >;
}

/** Reads saved widget visibility, merged over the defaults so newly-added widgets default on. */
export function loadWidgetVisibility(): Record<WidgetId, boolean> {
  const defaults = defaultVisibility();
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaults;
    const parsed = JSON.parse(raw) as Partial<Record<WidgetId, boolean>>;
    return { ...defaults, ...parsed };
  } catch {
    return defaults;
  }
}

export function saveWidgetVisibility(visibility: Record<WidgetId, boolean>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(visibility));
  } catch {
    // localStorage unavailable (private mode, quota, etc.) — visibility still
    // works for this session, it just won't persist across reloads.
  }
}
