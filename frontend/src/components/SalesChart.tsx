import { useMemo } from "react";
import { useI18n } from "../i18n";
import type { DashboardSummary } from "../types";

type SalesChartProps = {
  summary: DashboardSummary | null;
};

function isToday(isoDate: string): boolean {
  return isoDate === new Date().toISOString().slice(0, 10);
}

export function SalesChart({ summary }: SalesChartProps) {
  const { locale, money } = useI18n();

  const maxTrend = useMemo(() => {
    const values = summary?.sales_trend?.map((point) => Number(point.sales)) ?? [1];
    return Math.max(...values, 1);
  }, [summary]);

  const weekdayFormatter = useMemo(
    () =>
      new Intl.DateTimeFormat(locale, {
        weekday: locale.startsWith("fa") ? "narrow" : "short",
      }),
    [locale],
  );

  return (
    <div className="chart">
      {(summary?.sales_trend ?? []).map((point) => {
        const value = Number(point.sales);
        const height = maxTrend > 0 ? (value / maxTrend) * 100 : 0;
        const label = weekdayFormatter.format(new Date(point.date));

        return (
          <div className="bar-column" key={point.date}>
            <span className="chart-value">{money(value)}</span>
            <div className={`bar-track ${isToday(point.date) ? "today" : ""}`}>
              <span style={{ height: `${Math.max(height, 2)}%` }} />
            </div>
            <small>{label}</small>
          </div>
        );
      })}
    </div>
  );
}
