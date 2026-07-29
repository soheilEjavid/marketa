import { useMemo } from "react";
import { useI18n } from "../i18n";
import type { ProfitTrendPoint } from "../types";

type ProfitChartProps = {
  data?: ProfitTrendPoint[];
};

export function ProfitChart({ data = [] }: ProfitChartProps) {
  const { locale, money, t } = useI18n();

  const maxProfit = useMemo(() => {
    const values = data.map((point) => Number(point.profit));
    return Math.max(...values, 1);
  }, [data]);

  const weekdayFormatter = useMemo(
    () =>
      new Intl.DateTimeFormat(locale, {
        weekday: locale.startsWith("fa") ? "narrow" : "short",
      }),
    [locale],
  );

  if (data.length === 0) {
    return <div className="empty-state compact">{t("noData") || "No data yet"}</div>;
  }

  return (
    <div className="chart">
      {data.map((point) => {
        const value = Number(point.profit);
        const height = maxProfit > 0 ? (Math.abs(value) / maxProfit) * 100 : 0;
        const label = weekdayFormatter.format(new Date(point.date));
        const sign = value > 0 ? "positive" : value < 0 ? "negative" : "";

        return (
          <div className="bar-column" key={point.date}>
            <strong className={`chart-value ${sign}`}>{money(value)}</strong>
            <div className="bar-track">
              <span style={{ height: `${Math.max(height, 2)}%` }} />
            </div>
            <small>{label}</small>
          </div>
        );
      })}
    </div>
  );
}
