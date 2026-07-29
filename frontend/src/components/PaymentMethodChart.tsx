import { useEffect, useMemo, useState } from "react";
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { getPaymentMethodBreakdown } from "../api";
import { useI18n } from "../i18n";
import type { PaymentMethodBreakdownRow } from "../types";

type Period = "this-week" | "this-month" | "last-30";

// Validated categorical triple (dataviz skill, --pairs all, light mode): brand
// orange + blue + aqua all clear the CVD and normal-vision separation floors.
// Reusing only orange (the existing brand color) and red/green from the app's
// root palette failed validation — red vs orange is below the normal-vision
// floor, so this chart carries two small supporting hues used only here.
const COLORS: Record<string, string> = {
  cash: "#f97316",
  card: "#2a78d6",
  credit: "#1baf7a",
  mixed: "#8a766a",
};

function periodRange(period: Period): { fromDate: string; toDate: string } {
  const today = new Date();
  const toDate = today.toISOString().slice(0, 10);
  const from = new Date(today);
  if (period === "this-month") {
    from.setDate(1);
  } else if (period === "last-30") {
    from.setDate(from.getDate() - 29);
  } else {
    from.setDate(from.getDate() - 6);
  }
  return { fromDate: from.toISOString().slice(0, 10), toDate };
}

type PaymentMethodChartProps = {
  /** Fetches nothing until true — keeps hidden widgets from making API calls. */
  enabled: boolean;
};

export function PaymentMethodChart({ enabled }: PaymentMethodChartProps) {
  const { t, money } = useI18n();
  const [period, setPeriod] = useState<Period>("this-month");
  const [rows, setRows] = useState<PaymentMethodBreakdownRow[] | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    setLoading(true);
    const { fromDate, toDate } = periodRange(period);
    getPaymentMethodBreakdown({ fromDate, toDate })
      .then(setRows)
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [enabled, period]);

  const chartData = useMemo(
    () =>
      (rows ?? []).map((row) => ({
        name: t(row.payment_method),
        value: Number(row.total),
        method: row.payment_method,
      })),
    [rows, t],
  );

  const total = useMemo(() => chartData.reduce((sum, row) => sum + row.value, 0), [chartData]);

  if (!enabled) return null;

  return (
    <div>
      <select
        className="chart-period-select"
        value={period}
        onChange={(event) => setPeriod(event.target.value as Period)}
      >
        <option value="this-week">{t("thisWeek")}</option>
        <option value="this-month">{t("thisMonth")}</option>
        <option value="last-30">{t("last30Days")}</option>
      </select>

      {loading || rows === null ? (
        <div className="empty-state compact">{t("loading")}</div>
      ) : chartData.length === 0 ? (
        <div className="empty-state compact">{t("noData")}</div>
      ) : (
        <div className="donut-chart-wrap">
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <defs>
                {chartData.map((entry) => {
                  const color = COLORS[entry.method] ?? "#8a766a";
                  return (
                    <linearGradient id={`donutGradient-${entry.method}`} key={entry.method} x1="0" y1="0" x2="1" y2="1">
                      <stop offset="0%" stopColor={color} stopOpacity={1} />
                      <stop offset="100%" stopColor={color} stopOpacity={0.72} />
                    </linearGradient>
                  );
                })}
              </defs>
              <Pie
                data={chartData}
                dataKey="value"
                nameKey="name"
                innerRadius={54}
                outerRadius={82}
                paddingAngle={3}
                cornerRadius={8}
                strokeWidth={0}
              >
                {chartData.map((entry) => (
                  <Cell key={entry.method} fill={`url(#donutGradient-${entry.method})`} />
                ))}
              </Pie>
              <Legend verticalAlign="bottom" height={36} />
              <Tooltip
                formatter={(value) => money(Number(value))}
                contentStyle={{
                  borderRadius: 12,
                  border: "1px solid #f1ded2",
                  fontSize: 12,
                  boxShadow: "0 12px 28px rgba(179, 83, 20, .14)",
                  padding: "8px 12px",
                }}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="donut-chart-center">
            <span>{t("total")}</span>
            <strong>{money(total)}</strong>
          </div>
        </div>
      )}
    </div>
  );
}
