import { useEffect, useState } from "react";
import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getTopProducts } from "../api";
import { useI18n } from "../i18n";
import type { TopProductRow } from "../types";

type Metric = "quantity" | "profit";

type TopProductsChartProps = {
  /** Fetches nothing until true — keeps hidden widgets from making API calls. */
  enabled: boolean;
};

const BAR_COLORS = ["#f97316", "#fb923c", "#fdba74", "#fed7aa", "#ffedd5"];

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

  const chartData = (rows ?? []).map((row) => ({
    name: row.product_name,
    value: metric === "quantity" ? Number(row.total_quantity) : Number(row.total_profit),
  }));

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
      ) : chartData.length === 0 ? (
        <div className="empty-state compact">{t("noData")}</div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={chartData} layout="vertical" margin={{ top: 4, right: 48, left: 4, bottom: 4 }}>
            <XAxis type="number" hide />
            <YAxis
              type="category"
              dataKey="name"
              width={120}
              tick={{ fontSize: 11, fill: "#8a766a" }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              formatter={(value) => formatValue(Number(value))}
              cursor={{ fill: "rgba(249, 115, 22, .06)" }}
              contentStyle={{
                borderRadius: 12,
                border: "1px solid #f1ded2",
                fontSize: 12,
                boxShadow: "0 12px 28px rgba(179, 83, 20, .14)",
                padding: "8px 12px",
              }}
            />
            <Bar dataKey="value" radius={[0, 10, 10, 0]} barSize={20} isAnimationActive animationDuration={600}>
              {chartData.map((entry, index) => (
                <Cell key={entry.name} fill={BAR_COLORS[index] ?? BAR_COLORS[BAR_COLORS.length - 1]} />
              ))}
              <LabelList
                dataKey="value"
                position="right"
                formatter={(value: unknown) => {
                  const numeric = Number(value);
                  return Number.isFinite(numeric) ? formatValue(numeric) : "";
                }}
                style={{ fill: "#c94f05", fontSize: 11, fontWeight: 700 }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
