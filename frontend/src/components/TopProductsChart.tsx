import { useEffect, useState } from "react";
import { getTopProducts } from "../api";
import { useI18n } from "../i18n";
import type { TopProductRow } from "../types";

type Metric = "quantity" | "profit";

type TopProductsChartProps = {
  /** Fetches nothing until true — keeps hidden widgets from making API calls. */
  enabled: boolean;
};

/**
 * A ranked bar list rather than a plotted bar chart.
 *
 * The previous version used a recharts horizontal BarChart, which had two
 * problems this form removes outright:
 *
 *  - recharts lays out its category axis left-to-right regardless of the
 *    document's RTL direction, so Persian product names rendered *on top of*
 *    the bars they labelled.
 *  - each bar took a different step of orange. Products are nominal
 *    categories with no inherent order, so a lightness ramp across them
 *    re-encodes bar length as hue: it spends the only free visual channel
 *    restating what length already says, and the five steps are barely
 *    distinguishable from one another anyway. One series gets one colour.
 *
 * Giving the name its own line and the bar its own line means nothing can
 * collide at any name length, and the rank numeral carries identity without
 * relying on colour at all.
 */
export function TopProductsChart({ enabled }: TopProductsChartProps) {
  const { t, money, number } = useI18n();
  const [metric, setMetric] = useState<Metric>("quantity");
  const [rows, setRows] = useState<TopProductRow[] | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    setLoading(true);
    getTopProducts({ sortBy: metric, limit: 5 })
      .then(setRows)
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [enabled, metric]);

  if (!enabled) return null;

  const items = (rows ?? []).map((row) => ({
    name: row.product_name,
    value: metric === "quantity" ? Number(row.total_quantity) : Number(row.total_profit),
  }));
  // Share of the leader, so the top row always fills the track and the rest
  // read as a proportion of it — the comparison a "top products" list is for.
  const leader = items.length > 0 ? Math.max(...items.map((i) => i.value), 0) : 0;
  const formatValue = (value: number) => (metric === "quantity" ? number(value) : money(value));

  return (
    <div>
      <div className="chart-toggle-group">
        <button
          type="button"
          className={`chart-toggle-button ${metric === "quantity" ? "active" : ""}`}
          onClick={() => setMetric("quantity")}
        >
          {t("topByQuantity")}
        </button>
        <button
          type="button"
          className={`chart-toggle-button ${metric === "profit" ? "active" : ""}`}
          onClick={() => setMetric("profit")}
        >
          {t("topByProfit")}
        </button>
      </div>

      {loading || rows === null ? (
        <div className="empty-state compact">{t("loading")}</div>
      ) : items.length === 0 ? (
        <div className="empty-state compact">{t("noData")}</div>
      ) : (
        <ol className="rank-list">
          {items.map((item, index) => (
            <li className="rank-row" key={item.name}>
              <span className="rank-badge">{number(index + 1)}</span>
              <div className="rank-body">
                <div className="rank-line">
                  <span className="rank-name" title={item.name}>
                    {item.name}
                  </span>
                  <strong className="rank-value">{formatValue(item.value)}</strong>
                </div>
                <div className="rank-track">
                  <div
                    className="rank-fill"
                    style={{ width: `${leader > 0 ? Math.max((item.value / leader) * 100, 1.5) : 0}%` }}
                  />
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
